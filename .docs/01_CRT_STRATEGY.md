# 01 — Candle Range Theory Strategy

*Status: DRAFT — requirements only. No code until approved.*
*Parent: [CLAUDE.md](CLAUDE.md) · Read first: [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md)*

## Problem

The operator trades CRT by hand: find a higher-timeframe level, wait for
price to sweep liquidity past a candle's high or low, watch it snap back
inside the range, then enter. Judged by eye, one chart at a time.

That approach can't answer the only question that matters — **does this have
an edge?** — because there's no way to replay it over years of data.

The system to run and test a strategy already exists here. CRT doesn't.

## Evidence

Assumption — **no track record exists, live or backtested.** The rules below
are the operator's, transcribed from strategy notes. Nothing here is
validated. This milestone exists to produce the first real evidence either
way.

## Users

- **Primary**: The operator, testing CRT against futures data.

## Hypothesis

We believe **implementing CRT as a strategy plugin and running it through the
existing backtester** will **show whether CRT has a measurable edge**.
We'll know we're right when the backtest produces a trade log whose setups
the operator recognises as the ones they would have taken manually — and a
win rate, R multiple, and drawdown they can judge.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Setups match manual reading | Operator agrees with a sample of detected setups | Review detected setups against their own charts |
| Reproducible | Same data + settings → identical trade log | Re-run, compare |
| Stays inside runtime limits | `on_bar` never exceeds the 5s budget | No timeout kills across a full backtest |
| **Edge** | **TBD — the number this work exists to discover** | `engine/backtest/metrics.py`, walk-forward, Monte Carlo |

## The strategy

Implemented as a `StrategyBase` subclass (see
[00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md)).

### 1. Find the CRT candle

Only consider candles sitting at a **higher-timeframe point of interest** —
a supply/demand zone, a previous swing high or low, or a liquidity zone.

A CRT candle elsewhere on the chart is ignored. The level is what gives the
sweep meaning.

### 2. Wait for manipulation

Price must **sweep liquidity** past the CRT candle — above its high, or below
its low — and then **close back inside the range**. That snap back is the
V-shaped reaction. The candle that does the sweeping is the **liquidation
candle**.

No sweep, or a sweep that closes outside, is not a setup.

### 3. Enter — two selectable models

| Model | Behaviour |
|---|---|
| **Aggressive** | Enter immediately once the sweep closes back inside the range. |
| **Conservative** | Wait for price to pull back to the liquidation candle's demand/supply zone, or to an imbalance created by the move, then enter. |

Both are implemented; one is chosen by parameter via
`get_parameters_schema()`.

### 4. Take profit

The **opposing end of the CRT candle's range**. Swept the low → target the
high, and vice versa.

### 5. Stop loss

Slightly beyond the **extreme of the liquidation candle** — the actual sweep
wick — **not** the CRT candle's high or low.

This distinction is the point of the whole method: the liquidation candle is
the newly protected high/low. A stop at the CRT candle's edge sits inside the
zone price just proved it will reach.

### What the strategy emits

A `Signal` per setup, with CRT specifics in `metadata`: the HTF level, the
CRT candle's high and low, the liquidation candle's extreme, which entry
model fired, and the intended stop and target prices.

### Kelly inputs — an honest caveat

`StrategyBase` requires `get_win_probability()` and `get_win_loss_ratio()`.

The **win/loss ratio is genuinely derivable**: target is the far end of the
range, stop is just past the sweep, so R is known per setup.

**Win probability is not.** There's no data. It must return a conservative
placeholder, clearly marked, and be replaced once the backtest produces a
real number. A fabricated win rate driving position sizing would be worse
than no strategy at all.

## Scope

### In

- CRT detection: HTF level → sweep → close back inside.
- Both entry models, parameter-selectable.
- Stop and target per the rules above.
- Backtest runs through the existing
  `BacktestService → BacktestRunner → WalkForwardAnalyzer → MonteCarloSimulator`.

### Out

- Prop-firm rules, TradersPost execution, LLM evaluation, Pine Script export
  — all removed from scope (see [CLAUDE.md](CLAUDE.md)).
- Any live or funded trading. **This is backtest-only.** CRT will not place a
  real order, because nothing in scope connects it to a broker.
- Auto-tuning CRT's parameters.
- Tick-level precision — `on_tick` returns `[]`.

## Milestones

| # | Milestone | Outcome | Status |
|---|---|---|---|
| 0 | **Green test baseline** | Existing suite runs on Python 3.11/3.12 — proves the foundation before building on it | pending |
| 1 | HTF level identification | Points of interest computed from bar history | pending |
| 2 | Sweep + reaction detection | Emits CRT signals with full `metadata`, aggressive model | pending |
| 3 | Conservative entry | Pullback / imbalance entry, parameter-selectable | pending |
| 4 | Backtest on real ES data | Walk-forward + Monte Carlo results the operator can judge | pending |

Milestone 0 is first for a reason: if the existing tests don't pass, we'd be
building CRT on an unverified foundation and wouldn't know which layer broke.

## Open Questions

These need answers before or during implementation. The first is the big one.

- [ ] **How is a higher-timeframe point of interest defined in code?**
  Supply/demand and liquidity zones are discretionary when drawn by hand.
  Options: (a) the operator configures zones manually, (b) auto-detect from
  swing pivots, (c) a hybrid. **If this can't be pinned down, detection isn't
  reproducible and the backtest means nothing.** Recommend starting with (a)
  — manual zones — to get a working baseline, then attempting (b).
- [ ] **Which instrument and timeframes?** CRT needs an execution timeframe
  and a higher timeframe for levels. Which pair?
- [ ] **Where does intraday data come from?** `backtest_es_futures.py` uses
  yfinance **daily** bars. CRT intraday needs finer granularity than yfinance
  reliably provides. Either a data source is chosen, or the first backtest is
  daily-bar CRT — which is a real strategy, just not the one being described.
- [ ] **What exactly is a "created imbalance"** for the conservative entry —
  a standard fair-value gap, or something specific to the operator's method?
- [ ] **How far beyond the liquidation candle does the stop sit?** Fixed
  ticks, an ATR multiple, or a tunable parameter?
- [ ] Can higher-timeframe context be computed inside the 5-second `on_bar`
  budget, or does it need precomputing in `initialize()`?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| HTF levels too discretionary to automate | **High** | High | Start with operator-configured zones; treat auto-detection as later work |
| CRT has no edge once mechanised | Unknown | High | This is precisely what the milestone measures — and it's cheap to find out on paper |
| No usable intraday data | Medium | Medium | Settle the data source before writing detection; daily-bar CRT is the fallback |
| Placeholder win-probability taken as real | Medium | Medium | Mark it explicitly in code; replace with the backtested figure |
| Coded CRT quietly differs from the operator's actual method | **Medium** | High | Milestone 2 ends with a side-by-side review of detected setups against the operator's own charts, before building further |

---
*Status: DRAFT — requirements only. No code until approved.*
