# 01 — CRT Strategy Plugin

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md) · Prerequisite: [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md)*

## Problem

The operator trades Candle Range Theory manually — identifying higher
timeframe points of interest, watching for liquidity sweeps, judging the
V-shaped reaction by eye, then placing orders by hand. This is slow,
inconsistent under fatigue, and impossible to backtest systematically.

The strategy engine to run it already exists. What's missing is CRT itself:
`example_strategies/` contains only an RSI(2) mean-reversion reference.

## Evidence

Assumption — needs validation via backtest. **No live or backtested track
record exists for this CRT ruleset.** The setup criteria below come from the
operator's strategy notes, not from a coded implementation or a measured
edge. The purpose of this milestone is to make that edge *measurable*.

## Users

- **Primary**: The operator, running CRT against ES futures.
- **Not for**: Users needing a GUI strategy builder — configuration is via
  the existing `get_parameters_schema()` form generation.

## Hypothesis

We believe **implementing CRT as a `StrategyBase` plugin** will **let the
operator measure whether CRT has a real edge, and execute it without manual
error** for **the solo operator**.
We'll know we're right when a walk-forward backtest over real ES data
produces a trade log whose setups the operator recognises as the ones they
would have taken by hand.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Detection agreement with manual review | TBD — needs validation | Operator reviews a sample of detected setups against their own chart reading |
| Backtest reproducibility | Identical trade log for identical input | Re-run via `BacktestService`, diff output |
| Sandbox compliance | `on_bar` within the 5s budget on every bar | Existing runtime enforcement; no timeout kills in a full backtest |
| Edge (Sharpe, win rate, max DD) | TBD — the number this milestone exists to discover | `engine/backtest/metrics.py` + walk-forward |

## Scope

### MVP

Implement CRT as a `StrategyBase` subclass, honouring all existing runtime
constraints (sandboxed imports, 5s `on_bar` budget, no order placement, no
network/filesystem access).

**Detection logic:**

1. **Higher-timeframe point of interest.** Locate CRT candles only at HTF
   POIs — supply/demand zones, previous swing highs/lows, liquidity zones.
2. **Manipulation phase.** Price sweeps liquidity above the CRT candle's
   high (or below its low) and closes back inside the range — the V-shaped
   reaction.
3. **Entry models**, selectable via `get_parameters_schema()`:
   - *Aggressive* — enter immediately once the sweep closes back inside.
   - *Conservative* — wait for a pullback to the liquidation candle's
     demand/supply zone or to a created imbalance.
4. **Take-profit** — the opposing end of the CRT candle's range.
5. **Stop-loss** — slightly beyond the extreme of the **liquidation candle**
   (the actual sweep wick), *not* the CRT candle's high/low. The liquidation
   candle is the newly protected high/low; this distinction is the point.

**Signal emission:** return `Signal` objects with CRT specifics in
`metadata` — HTF POI reference, CRT candle high/low, liquidation candle
extreme, entry model used, intended stop price, intended target price.

> `metadata` is the agreed carrier for this data across three consumers: the
> LLM gate reads it as context ([04](04_LLM_TRADE_GATE.md)), the prop-firm
> sizer reads the stop distance ([02](02_PROP_FIRM_RISK.md)), and the
> connector turns stop/target into bracket parameters
> ([03](03_TRADERSPOST_CONNECTOR.md)). Its shape is a cross-document
> contract — changing it breaks all three.

**Kelly inputs:** `get_win_probability()` and `get_win_loss_ratio()` are
required by `StrategyBase`. CRT's win/loss ratio is *structurally* derivable
— the target is the opposite end of the range and the stop is just past the
sweep, so R is known per setup. Win probability has no basis until backtest
data exists; until then it must return a conservative placeholder and the
strategy must not rely on Kelly for sizing (see
[02_PROP_FIRM_RISK.md](02_PROP_FIRM_RISK.md), where prop-firm sizing
supersedes Kelly for futures).

**Backtesting:** drive CRT through the existing
`BacktestService → BacktestRunner → WalkForwardAnalyzer → MonteCarloSimulator`
chain, using `scripts/backtest_es_futures.py` as the data-loading template.

### Out of scope

- **Pine Script export** — deferred until the Python detection logic is
  validated. Exporting unvalidated logic to TradingView would duplicate an
  unproven implementation in a second language. Revisit once backtest
  results exist.
- Strategies other than CRT.
- Auto-optimization of CRT parameters.
- Intrabar/tick-level entry precision — `on_tick` returns `[]` initially.

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 0 | Green test baseline | Existing suite runs on a supported Python; CRT work starts from known-good | pending | — |
| 1 | HTF POI identification | Points of interest computed from bar history | pending | — |
| 2 | Sweep + V-reaction detection | Emits CRT setups with full `metadata`, aggressive model | pending | — |
| 3 | Conservative entry model | Pullback-to-zone / imbalance entry selectable by parameter | pending | — |
| 4 | Backtest on real ES data | Walk-forward + Monte Carlo trade log the operator can judge | pending | — |

## Open Questions

- [ ] **How is an HTF point of interest defined algorithmically?** Highest-risk
  unknown — supply/demand and liquidity zones are discretionary when drawn by
  hand. Options: operator-configured static zones, auto-detected swing pivots,
  or a hybrid. This choice determines whether detection is reproducible at all.
- [ ] What instrument and timeframe pair does the MVP target — ES on which
  execution timeframe, against which HTF for POIs?
- [ ] `backtest_es_futures.py` pulls **daily** bars from yfinance. CRT
  intraday almost certainly needs finer granularity than yfinance provides.
  What is the intraday futures data source?
- [ ] Precise definition of "created imbalance" for the conservative entry —
  standard fair-value-gap, or operator-specific?
- [ ] How far beyond the liquidation candle extreme does the stop sit — fixed
  ticks, ATR multiple, or a parameter?
- [ ] Can HTF context be computed inside a 5s `on_bar` budget, or does it need
  precomputation in `initialize()` / cached state?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| HTF POI detection too discretionary to automate | **High** | High | Start with operator-configured zones; treat auto-detection as a later milestone |
| CRT has no real edge once mechanised | Unknown (assumption) | High | This milestone exists to find out, on paper, before capital is committed |
| Intraday futures data unavailable/costly | Medium | Medium | Resolve data source before building detection; daily-bar CRT may be a fallback |
| Placeholder Kelly inputs mislead sizing | Medium | High | Prop-firm sizing supersedes Kelly for futures; never let a placeholder win-probability drive real size |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
