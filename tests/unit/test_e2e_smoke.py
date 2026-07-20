"""End-to-end smoke test wiring every M4 piece together exactly as they'd run
as separate processes in deployment: the TradingView webhook receiver signs
and queues a signal into Redis; the Engine drains it, runs the signal through
the full 13-step risk pipeline, and fills it via PaperConnector; the Engine
API exposes the resulting position; and the watchdog independently detects a
stalled Engine and emergency-flattens through the shared repository/Redis —
all without a real Postgres or network (fakeredis + InMemoryTradeRepository),
consistent with every other M4 test.
"""

import json
from datetime import datetime, timedelta, timezone

import fakeredis
import httpx
import pytest

from common import redis_keys
from common.enums import AssetClass, Timeframe
from engine.api.app import create_app as create_engine_app
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.core.engine import AlgorithmEngine
from engine.core.execution_manager import ExecutionManager
from engine.core.heartbeat import HeartbeatWriter
from engine.core.repository import InMemoryTradeRepository
from engine.core.signal_scheduler import SignalScheduler
from engine.core.state_manager import StateManager
from engine.risk.breaker import BreakerManager
from engine.risk.correlation import CorrelationManager
from engine.risk.position_sizer import PositionSizer
from engine.risk.risk_config import RiskConfig
from engine.risk.risk_manager import RiskManager
from engine.risk.safe_mode import SafeModeManager
from engine.strategy.serialization import encode_config
from sdk.ate_smp.models.strategy_config import StrategyConfig
from watchdog.heartbeat_watchdog import HeartbeatWatchdog
from webhook.app import create_app as create_webhook_app
from webhook.security import compute_signature

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
WEBHOOK_SECRET = "e2e-test-secret"


@pytest.mark.asyncio
async def test_tradingview_signal_to_paper_fill_to_api_to_dead_man_switch(tmp_path, monkeypatch):
    audit_file = tmp_path / "decision_audit.jsonl"
    monkeypatch.setattr("engine.risk.risk_manager.decision_audit_path", lambda: str(audit_file))

    # ----- Shared infrastructure: one Redis, one repository, exactly as the
    # webhook receiver, Engine, and watchdog would share them in deployment -----
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    repo = InMemoryTradeRepository()

    feed = ReplayPriceFeed()
    connector = PaperConnector(
        "paper1", AssetClass.CRYPTO, feed, TransactionCostModel(), initial_capital=100_000.0
    )
    await connector.connect({})
    feed.set_price("BTC/USD", 50_000.0)

    risk_config = RiskConfig()
    risk_manager = RiskManager(risk_config, PositionSizer(risk_config), SafeModeManager(risk_config))
    engine = AlgorithmEngine(
        connectors={"paper1": connector},
        risk_manager=risk_manager,
        breaker_manager=BreakerManager(risk_config),
        correlation_manager=CorrelationManager(risk_config),
        execution_manager=ExecutionManager({"paper1": connector}, repo),
        state_manager=StateManager(redis_client, repo),
        scheduler=SignalScheduler(),
        heartbeat=HeartbeatWriter(redis_client, interval_seconds=5, ttl_seconds=15),
        repository=repo,
        redis_client=redis_client,
    )

    strategy_config = StrategyConfig(
        asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,), connector_id="paper1"
    )
    await engine.load_strategy("strat_tv", strategy_config)  # webhook-driven, no subprocess

    # ----- Step 1: a signed TradingView alert arrives at the webhook receiver -----
    webhook_app = create_webhook_app(redis_client, WEBHOOK_SECRET)
    webhook_transport = httpx.ASGITransport(app=webhook_app)
    async with httpx.AsyncClient(transport=webhook_transport, base_url="http://webhook") as webhook_client:
        payload = json.dumps(
            {"strategy_id": "strat_tv", "asset": "BTC/USD", "direction": "long", "strength": 1.0}
        ).encode()
        signature = compute_signature(WEBHOOK_SECRET, payload)
        resp = await webhook_client.post(
            "/webhook/tradingview", content=payload, headers={"X-TV-Signature": signature}
        )
        assert resp.status_code == 200

    # The webhook receiver only ever touches Redis — confirm the signal is
    # really sitting in the queue the Engine will drain, independent of the
    # Engine process entirely.
    assert await redis_client.llen(redis_keys.SIGNAL_QUEUE) == 1

    # ----- Step 2: the Engine's next cycle drains the queue and runs the full
    # 13-step pre-trade risk pipeline before filling via PaperConnector -----
    await engine.run_cycle(T0)

    position = await connector.get_position("BTC/USD")
    assert position is not None
    assert position.quantity > 0
    open_trades = await repo.get_open_trades("strat_tv")
    assert len(open_trades) == 1

    # Every risk check that ran is in the immutable decision audit trail
    # (DOC 2 SS8) — confirm the approved decision was actually logged, not just
    # that the fill happened.
    assert audit_file.exists()
    with open(audit_file, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    matching = [r for r in records if r["asset"] == "BTC/USD" and r["strategy_id"] == "strat_tv"]
    assert matching, "expected the webhook-sourced signal's decision in the audit trail"
    approved_decision = matching[-1]
    assert approved_decision["approved"] is True
    assert len(approved_decision["checks"]) == 13  # every DOC 4 SS9 pipeline step ran
    assert all(c["passed"] for c in approved_decision["checks"])

    # ----- Step 3: the Engine API exposes the resulting position to whatever
    # would be the Dashboard Backend / Hermes in production -----
    engine_app = create_engine_app(engine)
    engine_transport = httpx.ASGITransport(app=engine_app)
    async with httpx.AsyncClient(transport=engine_transport, base_url="http://engine") as engine_client:
        resp = await engine_client.get("/engine/state")
        state = resp.json()
        assert state["open_position_count"] == 1
        assert state["strategies"]["strat_tv"]["webhook_driven"] is True

    # ----- Step 4: the Engine writes its heartbeat as part of the cycle that
    # just ran -----
    assert await redis_client.get(redis_keys.HEARTBEAT_KEY) is not None

    # ----- Step 5: the Engine "goes down" (stops writing heartbeats) and the
    # independent watchdog — sharing only Redis + the repository, never the
    # Engine's in-memory state — detects the sustained outage and flattens -----
    await redis_client.delete(redis_keys.HEARTBEAT_KEY)
    watchdog = HeartbeatWatchdog(redis_client, repo, heartbeat_timeout_seconds=300, check_interval_seconds=5)
    await watchdog.check_once(T0)  # establishes the last-healthy baseline

    triggered = await watchdog.check_once(T0 + timedelta(seconds=301))
    assert triggered

    # The repository (the source of truth the real Engine would reconcile
    # against on restart, per StateManager.recover_state) now shows the
    # position closed and safe mode active — even though the Engine process
    # itself never ran another cycle.
    assert await repo.get_open_trades("strat_tv") == []
    safe_mode_hash = await redis_client.hgetall(redis_keys.STATE_SAFE_MODE)
    assert safe_mode_hash["triggered_by"] == "dead_man_switch"
    assert safe_mode_hash["requires_manual_restart"] == "True"
