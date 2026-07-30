# 00 — Architecture As-Built

*Re-derived by reading source at commit `93a776b`. Replaces the missing DOC 1–5.*
*Parent: [CLAUDE.md](CLAUDE.md)*

This document describes **what exists today**, so the four extension
documents can reference real contracts instead of inventing new ones. It is
descriptive, not aspirational — where behaviour is unverified, it says so.

## Build history

| Milestone | Commit | Delivered |
|---|---|---|
| M0 | `9b2abe9` | Scaffolding, data foundation |
| M1 | `22d3641` | Strategy SDK, sandbox, subprocess runtime |
| M2 | `8e0f32e` | Risk layer — Kelly sizing, breakers, safe mode, correlation |
| M3 | `a9c4f61` | Backtester — cost model, walk-forward, Monte Carlo, sensitivity, regime, data quality |
| M4 | `3025707`, `5daf0eb` | Engine core, paper connector, TradingView webhook, watchdog |
| M5 | `a101367` | Dashboard backend — auth, services, Telegram |
| M6 | `06b172e`, `16cda68`, `e527a04` | CCXTConnector, React dashboard, Hermes agent |

## Process topology

Independently restartable processes (per `docker-compose.yml` and the module
entry points):

| Process | Module | Role |
|---|---|---|
| Engine | `engine/` | Owns strategies, risk, execution. The only thing that places orders. |
| Dashboard backend | `backend/` | FastAPI — auth, strategy/backtest/connector management |
| Frontend | `frontend/` | React + Vite + Tailwind |
| Webhook receiver | `webhook/` | FastAPI on :8080, **inbound** TradingView alerts → Redis queue |
| Watchdog | `watchdog/` | Heartbeat monitor, dead-man switch |
| Hermes | `hermes/` | LLM orchestration agent — scheduling, memory, Telegram |

Coupling is via Redis (`common/redis_keys.py`) and Postgres
(`engine/persistence/`, Alembic migrations).

> **Directionality matters.** `webhook/` is *inbound* — it receives alerts
> and writes to `engine:signal_queue`. TradersPost requires *outbound* calls
> from the bot. `webhook/` is therefore **not reusable** for TradersPost;
> see [03_TRADERSPOST_CONNECTOR.md](03_TRADERSPOST_CONNECTOR.md).

## Contract 1 — `StrategyBase` (`sdk/ate_smp/strategy_base.py`)

Abstract base every strategy implements. The engine never imports a strategy
directly; it communicates across a subprocess IPC boundary
(`engine/strategy/runtime.py`).

Required methods: `initialize`, `on_bar`, `on_tick`, `on_fill`,
`get_parameters_schema`, `get_win_probability`, `get_win_loss_ratio`,
`get_state`, `set_state`.

Enforced constraints:
- **Sandboxed imports** — stdlib + numpy/pandas/statsmodels/scipy/ta only
  (`engine/strategy/sandbox.py`).
- **5-second budget** on `on_bar`, or the strategy is killed and restarted
  from last persisted state.
- **Strategies cannot place orders.** They return `Signal` objects only. No
  network, no filesystem, no cross-strategy state access.

`get_win_probability` / `get_win_loss_ratio` feed the Kelly criterion — a
CRT strategy must supply these even though CRT sizing is prop-firm-driven.
See [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) for how that tension resolves.

## Contract 2 — `Signal` (`sdk/ate_smp/models/signal.py`)

```
Signal(timestamp, asset, direction: Direction, strength: float[0..1],
       limit_price: float|None, metadata: dict)
```

Frozen dataclass. `strength` is validated to `[0.0, 1.0]`.

**`metadata` is the extension point.** It is an untyped dict, so CRT-specific
fields (HTF point of interest, CRT candle bounds, liquidation-candle extreme,
entry model, intended stop/target) ride along without changing the contract.
This is what the LLM gate reads and what the TradersPost connector turns into
stop/target parameters.

## Contract 3 — `ConnectorBase` (`engine/connectors/base.py`)

Unified venue abstraction. Its own docstring: *"Every
broker/exchange/**prop-firm**/prediction-market adapter implements this
interface."* Prop firms were anticipated by the original design.

Required: `connect`, `disconnect`, `is_connected`, `get_historical_bars`,
`subscribe_live_data`, `get_live_quote`, `place_order`, `cancel_order`,
`modify_order`, `get_order_status`, `get_position`, `get_all_positions`,
`get_account_balance`, `get_fee_schedule`, `get_supported_assets`,
`get_capabilities`.

Existing implementations: `ccxt_connector.py` (crypto), `paper.py`
(simulation). Supporting pieces: `position_book.py`, `price_feed.py`.

`ConnectorCapabilities` advertises `supports_short`, `supports_stop`,
`supports_partial_fills`, `max_leverage`, `rate_limit_per_minute`.

## Contract 4 — `Order` / `Fill` (`engine/models/order.py`)

```
Order(asset, side: OrderSide, order_type: OrderType, quantity,
      limit_price?, stop_price?, time_in_force, client_order_id,
      venue_order_id?, status: OrderStatus, metadata)
```

Validated in `__post_init__`: positive quantity; `LIMIT`/`STOP_LIMIT` require
`limit_price`; `STOP`/`STOP_LIMIT` require `stop_price`.

**Gap for CRT:** `Order` models a *single* order with one stop price. CRT
needs a bracket — entry + protective stop + take-profit target. There is no
native bracket/OCO concept. Resolving this is a named open question in
[03_TRADERSPOST_CONNECTOR.md](03_TRADERSPOST_CONNECTOR.md).

## Contract 5 — the pre-trade risk pipeline (`engine/risk/risk_manager.py`)

`RiskManager.check_pre_trade(ctx: PreTradeContext) -> RiskDecision` runs
**13 sequential checks**, short-circuiting on first failure:

```
1. strategy_status      8.  position_sizing (Kelly, entry only)
2. safe_mode            9.  gross_exposure
3. daily_loss_breaker   10. leverage
4. drawdown_ceiling     11. capital_allocation
5. position_limit       12. minimum_portfolio
6. correlation          13. connector_health
7. regime_filter
```

Every check appends a `RiskCheckResult(name, passed, detail)`. The resulting
`RiskDecision` is written to an **append-only decision audit trail**
(`write_decision_audit`, 7-year retention per the cited DOC 2 §8).

Deliberate design details worth preserving:
- **Exits are never blocked** by sizing, correlation, exposure, or leverage
  checks — the code comments that blocking an exit is "the one time you most
  need to be able to get out."
- Rejection rationale is the failing check's `detail`.

**This pipeline is the insertion point for both extensions.** Prop-firm rule
checks and the LLM gate become additional checks with the same result shape
and the same audit trail — no new parallel gate. See
[02_PROP_FIRM_RISK.md](02_PROP_FIRM_RISK.md) and
[04_LLM_TRADE_GATE.md](04_LLM_TRADE_GATE.md).

## Contract 6 — risk configuration (`engine/risk/risk_config.py`)

`RiskConfig` is a flat dataclass of 23 fields with a `RANGES` table
validating each on load. Representative values:

| Field | Default | Valid range |
|---|---|---|
| `kelly_multiplier` | 0.25 | 0.10–0.50 |
| `max_risk_per_trade` | 0.02 | 0.005–0.03 |
| `daily_loss_breaker` | −0.03 | −0.05 to −0.01 |
| `max_drawdown` | 0.15 | 0.10–0.20 |
| `max_concurrent_positions` | 3 | 1–10 |

**Every value is a fraction of portfolio.** Prop firms enforce *absolute
dollar* trailing drawdown and daily-loss caps. This is the core semantic
mismatch driving [02_PROP_FIRM_RISK.md](02_PROP_FIRM_RISK.md).

Risk parameters are human-controlled only — the docstring notes Hermes may
propose strategy parameter changes but **never** risk parameters. Preserve
this: the LLM gate may only *reject* trades, never *relax* limits.

## Contract 7 — execution and state

- `engine/core/execution_manager.py` — places orders, converts filled orders
  to `Fill`s, records open/close against `TradeRepository`. Computes
  `realized_pnl` onto `fill.metadata` so the daily-loss breaker sees closed
  losses. **No pyramiding: one position per (strategy_id, asset).**
- `engine/core/state_manager.py`, `repository.py`, `market_history.py`,
  `heartbeat.py`, `signal_scheduler.py` — engine lifecycle.
- `engine/persistence/` + `alembic/` — Postgres schema and migrations.
- `watchdog/heartbeat_watchdog.py` — dead-man switch.

## Contract 8 — backtester (`engine/backtest/`)

`runner.py`, `metrics.py`, `walk_forward.py`, `monte_carlo.py`,
`cost_model.py`, `sensitivity.py`, `regime.py`, plus `data/quality.py`.

Driven via `backend/app/services/backtest_service.py`. `runner` applies the
same no-pyramiding, one-position-per-asset rule as the live engine — so
backtest and live behaviour agree.

`scripts/backtest_es_futures.py` already runs **real ES futures data**
(Yahoo `ES=F` via yfinance, daily bars) through this pipeline. It is the
template for CRT backtesting; its docstring notes no CME connector exists.

## Relevant enums already defined (`common/enums.py`)

The original design anticipated this work:

- `AssetClass.FUTURES`
- `RiskEventType.PROP_FIRM_RULE_WARNING`, `RiskEventType.PROP_FIRM_RULE_VIOLATION`
- `LaunchPhase.PAPER | SMALL | HALF | FULL` — the promotion path
- `DeploymentMode.PAPER | LIVE`
- `Direction.LONG | SHORT | EXIT_LONG | EXIT_SHORT | FLATTEN`

**No new enums are required for prop-firm risk events.** They exist and are
unused.

## Test suite

~50 modules under `tests/unit/` covering risk, backtest, engine core,
connectors, Hermes, auth, persistence. `pytest.ini` sets `asyncio_mode=auto`.
`fakeredis` is available, so Redis-dependent tests do not need a live server.

**Status: not executed in this environment.** Only Python 3.14 is installed;
`requirements.txt` pins numpy 1.26.4 / scipy 1.12.0 / psycopg2-binary 2.9.9,
none of which have 3.14 wheels. `psycopg2-binary` fails to build (no
`pg_config`). Getting a green baseline on Python 3.11/3.12 is a prerequisite
for all downstream work.

## Summary — reuse vs. build

| Capability | Status |
|---|---|
| Pluggable strategy engine, sandbox, hot-swap | **Reuse as-is** |
| Backtester (walk-forward, Monte Carlo, costs) | **Reuse as-is** |
| Futures historical data path | **Reuse** (`backtest_es_futures.py`) |
| Pre-trade risk pipeline + audit trail | **Reuse, extend with new checks** |
| State, persistence, watchdog, heartbeat | **Reuse as-is** |
| Dashboard, auth, Telegram alerting | **Reuse as-is** |
| Percentage/Kelly risk semantics | **Keep; add parallel prop-firm profile** |
| CRT strategy | **Build** |
| TradersPost connector | **Build** |
| LLM trade gate | **Build** |
| Bracket (entry+stop+target) order support | **Build — open design question** |
