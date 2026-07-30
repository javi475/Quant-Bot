# 02 — Pine Script Validation

*Status: DRAFT — requirements only. No code until approved.*
*Parent: [CLAUDE.md](CLAUDE.md) · Strategy rules: [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md)*

**This is now the first thing built.** Its job is to answer one question
before any bot exists: *does CRT actually have an edge?*

## Problem

CRT has no track record. Testing it in Python requires 15-minute ES history,
and the existing data path (yfinance) serves only about **60 days** at that
interval — enough to prove code runs, not enough to prove a strategy works.

Buying a futures data vendor solves it and costs money on top of everything
else. A TradingView subscription solves the same problem for a fee the
operator would pay anyway, and comes with a strategy tester attached.

So the subscription **is** the data purchase.

## Why this comes before the bot

If CRT has no edge, the cheapest possible way to discover that is a Pine
script and a subscription — not weeks of building a Python strategy, a
broker connector, and a VPS deployment first.

Building the bot before validating inverts the logic: automation removes
emotion from execution, but if the strategy is unprofitable, all it removes
is the emotion from losing money.

If CRT *does* have an edge, the Python version then gets written against
rules that are already proven, with a reference implementation to compare
against.

## Evidence

Assumption — no measured result exists yet. This milestone produces the first
one.

## Users

- **Primary**: The operator, reviewing backtest results on TradingView to
  decide whether to proceed.

## Hypothesis

We believe **implementing CRT in Pine Script and backtesting it on
TradingView** will **establish whether the strategy has an edge, before any
bot is built**.
We'll know we're right when the strategy tester produces a trade log the
operator recognises as their own setups, with performance statistics good
enough — or bad enough — to make the go/no-go decision obvious.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Signals match manual reading | Operator agrees with a sample of flagged setups | Visual review against their own charts |
| No repainting | Signals identical on live bars and historical replay | Bar replay comparison |
| Sample size | Enough trades for the result to mean something | Trade count over the tested period |
| **Edge** | **TBD — the number this exists to discover** | TradingView strategy tester |

## Scope

### In

- Both setups from [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md): continuation and
  reversal — **Setup A only once its stops and targets are defined**.
- The four computed levels: PDH, PDL, ONH, ONL.
- Candle-close-only logic; retest required before entry.
- US regular session filter; flat before close.
- Levels drawn on the chart so the operator can see what the script sees.

### Out

- Live order execution from Pine. TradingView alerts are not the execution
  path — that is phase 3 in Python.
- The monthly HTF zones (awareness only; not a trigger).
- Optimising parameters to make the backtest look good. See the overfitting
  risk below.

## The three things that make Pine backtests lie

These are the reason to build this deliberately rather than quickly. Each has
produced convincing backtests for strategies that lost money live.

**1. Repainting.** Pine can reference data that didn't exist at signal time,
making historical signals look prescient. The strategy must use only closed-
bar data — which the candle-close rule already enforces, if implemented
honestly.

**2. Intrabar fills.** By default the tester assumes fills inside a bar
without knowing the path price took. The CRT stop sits just beyond a wick,
so on any bar where both stop and target are touched, the tester may pick
the favourable one. **Bar Magnifier should be enabled**, and results without
it treated as optimistic.

**3. Overfitting.** With enough tuning any strategy looks good on a fixed
sample. Parameters should be set from the operator's actual method and left
alone. If they get tuned until results improve, the result measures the
tuning, not the strategy.

## Milestones

| # | Milestone | Outcome | Status |
|---|---|---|---|
| 1 | Levels on the chart | PDH/PDL/ONH/ONL computed and drawn correctly, session-aware | pending |
| 2 | Setup B (reversal) | Sweep + retest detection, entries/stops/targets, backtested | pending |
| 3 | Setup A definition | Stops and targets specified — currently the blocking gap | pending |
| 4 | Setup A (continuation) | Break + hold detection, backtested | pending |
| 5 | Go/no-go review | Operator reviews results and decides whether to build the bot | pending |

Milestone 1 is separate on purpose: if the levels are wrong by a session or
an hour, every downstream number is wrong in a way that still looks credible.

## Open Questions

- [ ] Which TradingView plan is needed for sufficient 15-minute ES history,
  and how far back does it actually go? This determines whether the sample is
  large enough to be meaningful.
- [ ] Is Bar Magnifier included in that plan?
- [ ] Which symbol — continuous ES futures, or a specific contract?
- [ ] What performance would count as good enough to proceed? Worth deciding
  *before* seeing results, so the bar isn't moved afterwards.
- [ ] All the strategy questions in
  [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md#open-questions) apply here first,
  since this is the implementation that hits them soonest.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Repainting produces a fake edge | **Medium** | **Critical** — would justify building a losing bot | Closed-bar data only; verify with bar replay before trusting any result |
| Intrabar fill assumptions flatter results | **Medium** | High | Enable Bar Magnifier; treat non-magnified results as optimistic |
| Overfitting to the available sample | Medium | High | Parameters from the operator's method, not from tuning; hold the bar fixed |
| Insufficient history for a meaningful sample | Medium | Medium | Confirm the plan's data depth before starting |
| Pine version drifts from the eventual Python version | Medium | Medium | [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) is the single source; cross-check signals when Python is built |

---
*Status: DRAFT — requirements only. No code until approved.*
