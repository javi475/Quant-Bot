# 00 — What Already Exists

*Derived by reading source at commit `93a776b`. Scope: only the parts CRT touches.*
*Parent: [CLAUDE.md](CLAUDE.md)*

This describes the existing system **as it actually is**, so the CRT spec can
reference real contracts instead of inventing new ones.

## Orientation

The repo contains "ATE-SMP", built across seven milestones (M0–M6):

| Milestone | Delivered |
|---|---|
| M0–M1 | Scaffolding; strategy SDK, sandbox, subprocess runtime |
| M2 | Risk layer — Kelly sizing, breakers, safe mode |
| M3 | Backtester — cost model, walk-forward, Monte Carlo, sensitivity |
| M4 | Engine core, paper connector, watchdog |
| M5–M6 | Dashboard backend + React frontend, ccxt connector, Hermes agent |

**Only two of these matter for CRT: the strategy SDK (M1) and the backtester
(M3).** The rest runs underneath and needs no changes.

> The code cites design documents — `DOC 2 §4`, `DOC 3 §1`, `DOC 4 §8` —
> that **are not in this repository**. This document was reconstructed from
> source, so it reflects what the code *does*, not necessarily what those
> documents specified.

## The one interface CRT must implement

`sdk/ate_smp/strategy_base.py` — `StrategyBase`, an abstract class.

Required methods:

| Method | Purpose |
|---|---|
| `initialize(config)` | Called once. Store config, precompute warmup state. |
| `on_bar(bar)` | **The core.** Receives one price bar, returns a list of `Signal`s. |
| `on_tick(tick)` | Tick-level entry point. Return `[]` if bar-only. |
| `on_fill(fill)` | Called after an order from your signal fills. |
| `get_parameters_schema()` | Declares tunable parameters; the dashboard builds a form from it. |
| `get_win_probability()` | Estimated win rate — feeds Kelly sizing. Must be 0.0–1.0. |
| `get_win_loss_ratio()` | Average win ÷ average loss. Must be > 0. |
| `get_state()` / `set_state()` | JSON-serializable state, for restart and hot-swap. |

Rules the runtime enforces:

- **Sandboxed imports** — stdlib plus numpy/pandas/statsmodels/scipy/ta only
  (`engine/strategy/sandbox.py`).
- **5-second limit** on `on_bar`, or the strategy is killed and restarted
  from its last saved state.
- **A strategy cannot place orders.** It returns `Signal` objects. No
  network, no filesystem, no access to other strategies' state.

That last rule is the key architectural fact: CRT decides *what* it wants;
the engine decides *whether and how* to act.

## What a strategy returns

`sdk/ate_smp/models/signal.py`:

```
Signal(timestamp, asset, direction: Direction, strength: float[0..1],
       limit_price: float|None, metadata: dict)
```

Frozen dataclass; `strength` is validated to `[0.0, 1.0]`.
`Direction` is `LONG | SHORT | EXIT_LONG | EXIT_SHORT | FLATTEN`.

**`metadata` is a free-form dict.** This is where CRT's specifics live —
the higher-timeframe level, the CRT candle's high/low, the liquidation
candle's extreme, which entry model fired, and the intended stop and target.
Nothing else needs to change to carry that information.

## The backtester

`engine/backtest/` — `runner.py`, `metrics.py`, `walk_forward.py`,
`monte_carlo.py`, `cost_model.py`, `sensitivity.py`, `regime.py`.

Driven through `backend/app/services/backtest_service.py`.

Two properties worth knowing:

- The runner enforces **one position per asset, no pyramiding** — the same
  rule the live engine uses, so backtest and live behaviour agree.
- `cost_model.py` applies trading costs, so results aren't fantasy fills.

**`scripts/backtest_es_futures.py` already works.** It pulls real ES futures
data (Yahoo `ES=F` via yfinance, **daily** bars) and runs it through this
full pipeline against the RSI reference strategy. It is the template for
backtesting CRT — and its daily-bar limitation is a real constraint (see the
data question in [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md)).

## Reference implementation to copy from

`example_strategies/rsi_mean_reversion.py` — the only existing strategy. It
shows the expected shape of a `StrategyBase` subclass and is the closest
thing to a template.

Tests worth reading before writing CRT:
`tests/unit/test_reference_strategy.py`, `test_backtest_runner.py`,
`test_sandbox.py`.

## Things that exist but CRT does not touch

Listed only so they aren't mistaken for missing work: the risk manager
(`engine/risk/`), connectors (`engine/connectors/` — ccxt and paper), the
engine core and state manager, the dashboard, the inbound TradingView
webhook receiver, the watchdog, and the Hermes agent.

CRT runs inside this machinery without modifying it.

## Test suite — status

~50 modules under `tests/unit/`. `pytest.ini` sets `asyncio_mode=auto`, and
`fakeredis` means Redis-backed tests need no live server.

**Never executed in this environment.** Only Python 3.14 is installed;
`requirements.txt` pins numpy 1.26.4, scipy 1.12.0, and psycopg2-binary 2.9.9,
none of which have 3.14 wheels — `psycopg2-binary` fails to build outright
(no `pg_config`).

Fixing this means installing Python 3.11 or 3.12 and building the venv there.
Until it's done, every claim in this document is **read from source, not
verified by running it**.

## Summary for CRT

| Need | Status |
|---|---|
| Strategy plugin interface | **Exists** — implement `StrategyBase` |
| Somewhere to put CRT's setup details | **Exists** — `Signal.metadata` |
| Backtest engine | **Exists** — walk-forward, Monte Carlo, costs |
| Real futures data path | **Exists (daily bars)** — `backtest_es_futures.py` |
| Working example to copy | **Exists** — `rsi_mean_reversion.py` |
| CRT itself | **Does not exist — this is the work** |
| Green test baseline | **Blocked** — Python version mismatch |
