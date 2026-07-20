"""The Algorithm Engine ("Brain") — DOC 2 §1, §5. Ties every prior milestone
together: strategy subprocesses (M1) and the TradingView webhook queue supply
signals; the risk layer (M2) gates every signal; PaperConnector (M4) executes
approved orders; StateManager/HeartbeatWriter persist state and prove
liveness.

`run_cycle()` is the single testable unit of work — it performs exactly one
pass of the pipeline and returns. `run()` is a thin wrapper that calls it
forever at `cycle_interval_seconds` (50ms per DOC 2 §5); tests call
`run_cycle()` directly so nothing here depends on real wall-clock timing.

Design notes worth remembering (see engine/core/execution_manager.py and
engine/backtest/runner.py for the same convention):
  - No pyramiding: one open position per (asset), tracked authoritatively in
    the TradeRepository via strategy_id — this is also what makes an
    EXIT_LONG/EXIT_SHORT/FLATTEN signal's execution quantity come from the
    *actual open position size*, not from a fresh Kelly calculation. The risk
    pipeline's position-sizing step (DOC 4 §9 step 8) still runs for exits —
    it's a sanity check that the sizing math doesn't error, not the exit
    order's real quantity.
  - Position limits/exposure/correlation are portfolio-wide (across every
    connector), matching DOC 4 §4's "each non-zero symbol counts once".
"""

from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any, Optional

from common.enums import (
    Direction,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskEventSeverity,
    RiskEventType,
)
from engine.backtest.regime import classify_trend, classify_volatility
from engine.connectors.base import ConnectorBase, ConnectorError
from engine.core.execution_manager import ExecutionManager
from engine.core.heartbeat import HeartbeatWriter
from engine.core.market_history import MarketHistoryTracker
from engine.core.repository import RiskEventRecord, TradeRepository
from engine.core.signal_scheduler import SignalScheduler
from engine.core.state_manager import StateManager
from engine.models.order import Fill, Order
from engine.models.position import Position
from engine.risk.breaker import BreakerManager
from engine.risk.correlation import CorrelationManager
from engine.risk.monitoring import check_max_loss_exit, compute_gross_exposure
from engine.risk.risk_manager import PreTradeContext, RiskManager
from engine.strategy.runtime import (
    StrategyCrashedError,
    StrategyProcess,
    StrategyProcessError,
    StrategyRuntimeError,
    StrategyTimeoutError,
)
from sdk.ate_smp.models.bar import Bar
from sdk.ate_smp.models.signal import FillNotification, Signal
from sdk.ate_smp.models.strategy_config import StrategyConfig

log = structlog.get_logger(service="engine")

# A webhook-driven "strategy" has no Python code to ask get_win_probability()/
# get_win_loss_ratio() of — TradingView alerts carry no win-rate track record.
# 0.5/1.0 is the Kelly break-even point (full_kelly = (p*(b+1)-1)/b = 0 exactly),
# which would silently reject every webhook-sourced trade at the position-sizing
# step forever. These defaults keep Kelly sizing modestly positive while still
# letting the alert's own `strength` field modulate size; an operator-tunable
# override belongs on StrategyConfig once the dashboard (M5) can set it.
DEFAULT_WEBHOOK_WIN_PROBABILITY = 0.55
DEFAULT_WEBHOOK_WIN_LOSS_RATIO = 1.5


class RunningStrategy:
    def __init__(
        self,
        strategy_id: str,
        config: StrategyConfig,
        connector_id: str,
        process: Optional[StrategyProcess] = None,
    ) -> None:
        self.strategy_id = strategy_id
        self.config = config
        self.connector_id = connector_id
        self.process = process  # None => TradingView-webhook-driven, no subprocess
        self.enabled = True
        self.win_probability = DEFAULT_WEBHOOK_WIN_PROBABILITY
        self.win_loss_ratio = DEFAULT_WEBHOOK_WIN_LOSS_RATIO


class AlgorithmEngine:
    def __init__(
        self,
        connectors: dict[str, ConnectorBase],
        risk_manager: RiskManager,
        breaker_manager: BreakerManager,
        correlation_manager: CorrelationManager,
        execution_manager: ExecutionManager,
        state_manager: StateManager,
        scheduler: SignalScheduler,
        heartbeat: HeartbeatWriter,
        repository: TradeRepository,
        redis_client: Any,
        cycle_interval_seconds: float = 0.05,
    ) -> None:
        self.connectors = connectors
        self.risk_manager = risk_manager
        self.breaker_manager = breaker_manager
        self.correlation_manager = correlation_manager
        self.execution_manager = execution_manager
        self.state_manager = state_manager
        self.scheduler = scheduler
        self.heartbeat = heartbeat
        self.repository = repository
        self.redis = redis_client
        self.cycle_interval_seconds = cycle_interval_seconds

        self.strategies: dict[str, RunningStrategy] = {}
        self.market_history = MarketHistoryTracker(lookback=max(200, risk_manager.config.correlation_lookback_days))
        self.last_prices: dict[str, float] = {}

        self._running = False
        self._daily_realized_pnl = 0.0
        self._daily_pnl_date = None
        self._halted = False

    # ----- Strategy lifecycle -----

    async def load_strategy(
        self,
        strategy_id: str,
        config: StrategyConfig,
        module_path: Optional[str] = None,
        class_name: Optional[str] = None,
    ) -> None:
        connector_id = config.connector_id
        if connector_id not in self.connectors:
            raise ValueError(f"unknown connector_id '{connector_id}' for strategy {strategy_id}")

        process = None
        if module_path and class_name:
            process = StrategyProcess(strategy_id, module_path, class_name)
            await process.start()
            await process.initialize(config)

            saved_state = await self.state_manager.load_strategy_state(strategy_id)
            if saved_state:
                await process.set_state(saved_state)

        running = RunningStrategy(strategy_id, config, connector_id, process)
        if process is not None:
            running.win_probability = await process.get_win_probability()
            running.win_loss_ratio = await process.get_win_loss_ratio()
            connector = self.connectors[connector_id]
            for symbol in config.symbols:
                for timeframe in config.timeframes:
                    self.scheduler.subscribe(connector, symbol, timeframe)

        self.strategies[strategy_id] = running
        log.info("strategy_loaded", strategy_id=strategy_id, webhook_driven=process is None)

    async def enable_strategy(self, strategy_id: str) -> None:
        running = self.strategies[strategy_id]
        running.enabled = True
        if running.process is not None:
            await running.process.on_strategy_enabled()

    async def disable_strategy(self, strategy_id: str) -> None:
        running = self.strategies[strategy_id]
        running.enabled = False
        if running.process is not None:
            await running.process.on_strategy_disabled()

    async def swap_strategy(self, strategy_id: str, module_path: str, class_name: str) -> None:
        """Hot-swap: state carries over via get_state()/set_state() (DOC 3 §7),
        target <=10s (US-006)."""
        running = self.strategies[strategy_id]
        state = None
        if running.process is not None:
            state = await running.process.get_state()
            await running.process.shutdown()

        new_process = StrategyProcess(strategy_id, module_path, class_name)
        await new_process.start()
        await new_process.initialize(running.config)
        if state:
            await new_process.set_state(state)

        running.process = new_process
        running.win_probability = await new_process.get_win_probability()
        running.win_loss_ratio = await new_process.get_win_loss_ratio()
        log.info("strategy_swapped", strategy_id=strategy_id)

    async def _handle_strategy_fault(self, strategy_id: str, reason: str, restart: bool) -> None:
        running = self.strategies.get(strategy_id)
        if running is None or running.process is None:
            return

        log.warning("strategy_fault", strategy_id=strategy_id, reason=reason, restart=restart)

        if restart:
            await running.process.kill()
            saved_state = await self.state_manager.load_strategy_state(strategy_id)
            new_process = StrategyProcess(strategy_id, running.process.module_path, running.process.class_name)
            await new_process.start()
            await new_process.initialize(running.config)
            if saved_state:
                await new_process.set_state(saved_state)
            running.process = new_process
        else:
            running.enabled = False
            await running.process.kill()

    # ----- Portfolio-wide read helpers -----

    async def _all_positions(self) -> dict[str, list[Position]]:
        return {cid: await c.get_all_positions() for cid, c in self.connectors.items()}

    async def _refresh_stale_prices(
        self, positions_by_connector: dict[str, list[Position]], priced_this_cycle: set[str]
    ) -> None:
        """Bar dispatch keeps `last_prices` fresh for subprocess-strategy
        assets, but a webhook-driven strategy's asset never gets a bar — its
        position would otherwise mark-to-market at its stale entry price
        forever, silently hiding real gains/losses from the breaker/drawdown/
        max-loss checks that all read `last_prices`. Fetch a live quote for
        every open position whose asset didn't already get a fresh bar THIS
        cycle (checking cache membership instead of `priced_this_cycle` would
        be wrong: once cached, an asset would never be refetched again)."""
        for connector_id, positions in positions_by_connector.items():
            connector = self.connectors[connector_id]
            for position in positions:
                if position.quantity == 0 or position.asset in priced_this_cycle:
                    continue
                try:
                    quote = await connector.get_live_quote(position.asset)
                    self.last_prices[position.asset] = quote.mid
                except ConnectorError:
                    pass  # no fresher price available; keep using the last known one

    def _mark(self, position: Position) -> float:
        return self.last_prices.get(position.asset, position.current_price)

    async def _compute_snapshot(self, positions_by_connector: dict[str, list[Position]]) -> tuple[float, float, float, int]:
        """Returns (equity, unrealized_pnl, gross_exposure_value, open_position_count)."""
        equity = 0.0
        unrealized = 0.0
        gross_exposure_value = 0.0
        count = 0
        for connector_id, connector in self.connectors.items():
            equity += await connector.get_account_balance()
            for position in positions_by_connector.get(connector_id, []):
                if position.quantity == 0:
                    continue
                mark = self._mark(position)
                market_value = position.quantity * mark
                equity += market_value
                unrealized += (mark - position.entry_price) * position.quantity
                gross_exposure_value += abs(market_value)
                count += 1
        return equity, unrealized, gross_exposure_value, count

    def _strategy_by_asset(self, connector_id: str) -> dict[str, str]:
        return {
            symbol: sid
            for sid, running in self.strategies.items()
            if running.connector_id == connector_id
            for symbol in running.config.symbols
        }

    async def _strategy_deployed_notional(self, strategy_id: str) -> float:
        open_trades = await self.repository.get_open_trades(strategy_id)
        return sum(abs(t.quantity * self.last_prices.get(t.asset, t.entry_price)) for t in open_trades)

    def _check_regime(self, running: RunningStrategy, asset: str) -> bool:
        regime_filter = running.config.regime_filter
        if regime_filter is None:
            return True

        closes = self.market_history.get_closes(asset)
        if len(closes) < regime_filter.sma_period:
            return True  # not enough history yet: allow rather than block indefinitely

        trend = classify_trend(closes, index=len(closes) - 1, sma_period=regime_filter.sma_period)
        if trend not in regime_filter.allowed_trend:
            return False

        highs, lows = self.market_history.get_highs(asset), self.market_history.get_lows(asset)
        volatility = classify_volatility(highs, lows, closes, index=len(closes) - 1)
        return volatility in regime_filter.allowed_volatility

    def _accumulate_realized_pnl(self, pnl: float, now: datetime) -> None:
        today = now.date()
        if self._daily_pnl_date != today:
            self._daily_pnl_date = today
            self._daily_realized_pnl = 0.0
        self._daily_realized_pnl += pnl

    # ----- Fill handling -----

    async def _on_fill(self, strategy_id: str, fill: Fill, now: datetime) -> None:
        running = self.strategies.get(strategy_id)
        if running is not None and running.process is not None:
            notification = FillNotification(
                order_id=fill.order_id,
                asset=fill.asset,
                quantity=fill.quantity,
                price=fill.price,
                status=OrderStatus.FILLED,
                timestamp=fill.timestamp,
            )
            try:
                await running.process.on_fill(notification)
            except StrategyProcessError as exc:
                log.warning("on_fill_notification_failed", strategy_id=strategy_id, error=str(exc))

        realized_pnl = fill.metadata.get("realized_pnl")
        if realized_pnl is not None:
            self._accumulate_realized_pnl(realized_pnl, now)

    # ----- Safe mode / breaker triggers -----

    async def _trigger_safe_mode(
        self, event_type: RiskEventType, halt_new_entries: bool, requires_manual_restart: bool, now: datetime, description: str
    ) -> None:
        self.risk_manager.safe_mode.activate(event_type.value, halt_new_entries, requires_manual_restart, now)
        await self.repository.record_risk_event(
            RiskEventRecord(
                event_type=event_type,
                severity=RiskEventSeverity.CRITICAL,
                description=description,
                action_taken="flatten_all; safe_mode activated",
                safe_mode_activated=True,
                occurred_at=now,
            )
        )
        for connector_id in self.connectors:
            strategy_map = self._strategy_by_asset(connector_id)
            fills = await self.execution_manager.flatten_all(connector_id, strategy_map)
            for fill in fills:
                await self._on_fill(strategy_map.get(fill.asset, ""), fill, now)

    # ----- The per-cycle pipeline -----

    async def run_cycle(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)

        new_bars = self.scheduler.drain_bars()
        for bars in new_bars.values():
            for bar in bars:
                self.market_history.on_bar(bar)
                self.last_prices[bar.asset] = bar.close

        pending_signals: list[tuple[str, Signal]] = []

        for strategy_id, running in list(self.strategies.items()):
            if running.process is None or not running.enabled:
                continue
            faulted = False
            for symbol in running.config.symbols:
                if faulted:
                    break
                for bar in new_bars.get(symbol, []):
                    try:
                        signals = await running.process.on_bar(bar)
                    except StrategyTimeoutError as exc:
                        await self._handle_strategy_fault(strategy_id, str(exc), restart=True)
                        faulted = True
                        break
                    except (StrategyCrashedError, StrategyRuntimeError) as exc:
                        await self._handle_strategy_fault(strategy_id, str(exc), restart=False)
                        faulted = True
                        break
                    pending_signals.extend((strategy_id, s) for s in signals)

        webhook_signals = await self.scheduler.drain_webhook_signals(self.redis)
        for strategy_id, signal in webhook_signals:
            running = self.strategies.get(strategy_id)
            if running is not None and running.enabled:
                pending_signals.append((strategy_id, signal))

        for connector_id in self.connectors:
            strategy_map = self._strategy_by_asset(connector_id)
            fills = await self.execution_manager.process_pending_orders(connector_id, strategy_map)
            for fill in fills:
                await self._on_fill(strategy_map.get(fill.asset, ""), fill, now)

        positions_by_connector = await self._all_positions()
        await self._refresh_stale_prices(positions_by_connector, priced_this_cycle=set(new_bars.keys()))
        equity, unrealized_pnl, gross_exposure_value, position_count = await self._compute_snapshot(positions_by_connector)
        gross_exposure_pct = gross_exposure_value / equity if equity > 0 else 0.0

        daily_result = self.breaker_manager.check_daily_loss(self._daily_realized_pnl, unrealized_pnl, equity, now)
        drawdown_result = self.breaker_manager.check_drawdown(equity)

        flattened_this_cycle = False

        if daily_result.newly_triggered and not self._halted:
            await self._trigger_safe_mode(
                RiskEventType.DAILY_LOSS_BREAKER,
                halt_new_entries=False,
                requires_manual_restart=False,
                now=now,
                description=f"Daily loss breaker triggered at {daily_result.daily_pnl_pct:.2%}",
            )
            flattened_this_cycle = True
        if drawdown_result.breached and drawdown_result.newly_escalated and not self._halted:
            await self._trigger_safe_mode(
                RiskEventType.DRAWDOWN_CEILING,
                halt_new_entries=True,
                requires_manual_restart=True,
                now=now,
                description=f"Drawdown ceiling breached at {drawdown_result.current_drawdown:.2%}",
            )
            flattened_this_cycle = True
        elif drawdown_result.newly_escalated and drawdown_result.alert_level:
            event_type = {
                "info": RiskEventType.DRAWDOWN_ALERT_1,
                "warning": RiskEventType.DRAWDOWN_ALERT_2,
                "serious": RiskEventType.DRAWDOWN_ALERT_3,
            }.get(drawdown_result.alert_level)
            if event_type:
                await self.repository.record_risk_event(
                    RiskEventRecord(
                        event_type=event_type,
                        severity=RiskEventSeverity.WARNING,
                        description=f"Drawdown alert ({drawdown_result.alert_level}) at {drawdown_result.current_drawdown:.2%}",
                        occurred_at=now,
                    )
                )

        if flattened_this_cycle:
            # A breaker just flattened the book — the snapshot taken above is
            # now stale. Re-fetch before anything downstream (signal
            # processing, in-trade monitoring) acts on positions that no
            # longer exist, which would otherwise re-close an already-flat
            # position and accidentally open one in the opposite direction.
            positions_by_connector = await self._all_positions()
            equity, unrealized_pnl, gross_exposure_value, position_count = await self._compute_snapshot(
                positions_by_connector
            )
            gross_exposure_pct = gross_exposure_value / equity if equity > 0 else 0.0

        all_positions_flat = [p for positions in positions_by_connector.values() for p in positions if p.quantity != 0]

        for strategy_id, signal in pending_signals:
            await self._process_signal(
                strategy_id, signal, now, equity, gross_exposure_pct, position_count,
                all_positions_flat, daily_result.triggered, drawdown_result.breached,
            )

        await self._monitor_positions(now, equity, positions_by_connector)

        await self.state_manager.persist_hot_state(
            equity=equity,
            daily_pnl_pct=daily_result.daily_pnl_pct,
            drawdown_pct=drawdown_result.current_drawdown,
            peak_equity=drawdown_result.peak_equity,
            gross_exposure_pct=gross_exposure_pct,
            safe_mode=self.risk_manager.safe_mode,
            now=now,
        )
        await self.heartbeat.maybe_write(now)

    async def _process_signal(
        self,
        strategy_id: str,
        signal: Signal,
        now: datetime,
        equity: float,
        current_gross_exposure: float,
        current_position_count: int,
        all_positions_flat: list[Position],
        daily_loss_breaker_triggered: bool,
        drawdown_breached: bool,
    ) -> None:
        running = self.strategies.get(strategy_id)
        if running is None:
            return

        connector = self.connectors[running.connector_id]
        is_entry = signal.direction in (Direction.LONG, Direction.SHORT)

        price = self.last_prices.get(signal.asset)
        if price is None:
            try:
                quote = await connector.get_live_quote(signal.asset)
                price = quote.mid
            except ConnectorError:
                return

        existing_position = next(
            (p for p in all_positions_flat if p.asset == signal.asset), None
        )

        correlation_result = None
        if is_entry:
            other_returns = {
                p.asset: self.market_history.get_returns(p.asset, self.risk_manager.config.correlation_lookback_days)
                for p in all_positions_flat
                if p.asset != signal.asset
            }
            if other_returns:
                new_returns = self.market_history.get_returns(
                    signal.asset, self.risk_manager.config.correlation_lookback_days
                )
                correlation_result = self.correlation_manager.check_correlation(new_returns, other_returns)

        capital_allocation_ok = True
        if is_entry:
            deployed = await self._strategy_deployed_notional(strategy_id)
            capital_allocation_ok = deployed < running.config.capital_allocation * equity

        ctx = PreTradeContext(
            asset=signal.asset,
            is_entry=is_entry,
            strategy_enabled=running.enabled,
            trading_mode_ok=True,
            now=now,
            portfolio_value=equity,
            price=price,
            signal_strength=signal.strength,
            win_probability=running.win_probability,
            win_loss_ratio=running.win_loss_ratio,
            current_position_count=current_position_count,
            current_gross_exposure=current_gross_exposure,
            daily_loss_breaker_triggered=daily_loss_breaker_triggered,
            drawdown_breached=drawdown_breached,
            regime_ok=self._check_regime(running, signal.asset),
            connector_healthy=connector.is_connected(),
            capital_allocation_ok=capital_allocation_ok,
            correlation_result=correlation_result,
            strategy_id=strategy_id,
        )
        decision = self.risk_manager.check_pre_trade(ctx)
        if not decision.approved:
            return  # RiskManager already wrote the audit log entry

        if signal.direction == Direction.LONG:
            side, quantity = OrderSide.BUY, decision.quantity
        elif signal.direction == Direction.SHORT:
            side, quantity = OrderSide.SELL, decision.quantity
        elif signal.direction in (Direction.EXIT_LONG, Direction.EXIT_SHORT, Direction.FLATTEN):
            if existing_position is None:
                return
            side = OrderSide.SELL if existing_position.quantity > 0 else OrderSide.BUY
            quantity = abs(existing_position.quantity)  # close the real position, not a fresh Kelly size
        else:
            return

        if quantity <= 0:
            return

        order = Order(asset=signal.asset, side=side, order_type=OrderType.MARKET, quantity=quantity)
        fill = await self.execution_manager.place_order(running.connector_id, order, strategy_id)
        if fill:
            await self._on_fill(strategy_id, fill, now)

    async def _monitor_positions(
        self, now: datetime, equity: float, positions_by_connector: dict[str, list[Position]]
    ) -> None:
        for connector_id, positions in positions_by_connector.items():
            strategy_map = self._strategy_by_asset(connector_id)
            for position in positions:
                if position.quantity == 0:
                    continue
                mark = self._mark(position)
                position.update_price(mark)
                if not check_max_loss_exit(position, equity, self.risk_manager.config.max_risk_per_trade):
                    continue

                strategy_id = strategy_map.get(position.asset, "")
                side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
                order = Order(asset=position.asset, side=side, order_type=OrderType.MARKET, quantity=abs(position.quantity))
                fill = await self.execution_manager.place_order(connector_id, order, strategy_id)
                if fill:
                    await self._on_fill(strategy_id, fill, now)
                    await self.repository.record_risk_event(
                        RiskEventRecord(
                            event_type=RiskEventType.MAX_LOSS_STOP,
                            severity=RiskEventSeverity.WARNING,
                            description=f"Forced max-loss exit on {position.asset}",
                            strategy_id=strategy_id,
                            symbol=position.asset,
                            occurred_at=now,
                        )
                    )

    # ----- Read-only snapshot for the API/WebSocket layer -----

    async def get_state_snapshot(self) -> dict[str, Any]:
        positions_by_connector = await self._all_positions()
        equity, unrealized_pnl, gross_exposure_value, position_count = await self._compute_snapshot(
            positions_by_connector
        )
        safe_mode = self.risk_manager.safe_mode
        return {
            "equity": equity,
            "unrealized_pnl": unrealized_pnl,
            "gross_exposure_value": gross_exposure_value,
            "open_position_count": position_count,
            "halted": self._halted,
            "safe_mode": {
                "active": safe_mode.is_active,
                "phase": safe_mode.phase.value,
                "triggered_by": safe_mode.triggered_by,
                "halt_new_entries": safe_mode.halt_new_entries,
                "requires_manual_restart": safe_mode.requires_manual_restart,
            },
            "strategies": {
                sid: {"enabled": r.enabled, "webhook_driven": r.process is None, "connector_id": r.connector_id}
                for sid, r in self.strategies.items()
            },
        }

    # ----- Lifecycle -----

    async def run(self) -> None:
        import asyncio

        self._running = True
        while self._running:
            await self.run_cycle()
            await asyncio.sleep(self.cycle_interval_seconds)

    async def halt(self) -> None:
        """Stops new entries but leaves existing positions open (manual halt)."""
        self._halted = True
        await self.repository.record_risk_event(
            RiskEventRecord(
                event_type=RiskEventType.MANUAL_HALT,
                severity=RiskEventSeverity.WARNING,
                description="Engine manually halted",
                occurred_at=datetime.now(timezone.utc),
            )
        )

    async def flatten(self) -> None:
        now = datetime.now(timezone.utc)
        for connector_id in self.connectors:
            strategy_map = self._strategy_by_asset(connector_id)
            fills = await self.execution_manager.flatten_all(connector_id, strategy_map)
            for fill in fills:
                await self._on_fill(strategy_map.get(fill.asset, ""), fill, now)

    async def kill(self) -> None:
        """Emergency stop: flatten everything, disable every strategy, halt."""
        await self.flatten()
        for strategy_id in list(self.strategies.keys()):
            await self.disable_strategy(strategy_id)
        self._halted = True
        await self.repository.record_risk_event(
            RiskEventRecord(
                event_type=RiskEventType.KILL_SWITCH,
                severity=RiskEventSeverity.CRITICAL,
                description="Kill switch activated",
                action_taken="flatten_all; all strategies disabled",
                occurred_at=datetime.now(timezone.utc),
            )
        )

    def stop(self) -> None:
        self._running = False
