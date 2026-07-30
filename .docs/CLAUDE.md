# Quant-Bot — Project Charter

*Scope: the CRT strategy, and nothing else. Requirements only — no code until approved.*

## The short version

This repository already contains a working trading system called **ATE-SMP**
(~216 files: strategy runtime, backtester, risk manager, dashboard, test
suite). It was built by earlier work in this repo.

It does **not** contain a Candle Range Theory strategy.

**That is the entire current goal: write CRT as one strategy plugin, and
backtest it.** The machine to run it already exists.

## Why this is a small job, not a big one

The existing system is built so strategies are plug-in modules. A strategy
is a single Python class that receives price bars and returns trade signals.
It does not place orders, manage risk, or talk to a broker — the engine
already does all of that.

So CRT is one file implementing one interface, plus a backtest run.

## What we are NOT doing right now

These were previously in scope and have been **removed**:

- Prop-firm rule enforcement (Lucid, Apex, Top One, Tradeify)
- TradersPost order execution
- AI/LLM trade evaluation
- Pine Script / TradingView export
- Live or funded-account trading of any kind

They are recoverable from git history at commit `5e6c713` if we return to
them. Until then, no document in `.docs/` should reference them as active
work.

**Consequence to be clear about:** with these removed, CRT is
**backtest-only**. It will not place a real trade, because nothing in scope
connects it to a broker. That is the intended state.

## Problem

The operator trades CRT by hand — spotting higher-timeframe levels, watching
for a liquidity sweep, judging the reaction by eye. It is slow, inconsistent,
and impossible to test systematically. There is no way to answer "does this
actually work?" without a coded version.

## Evidence

Assumption — **CRT has no track record here, live or backtested.** The rules
come from the operator's strategy notes. The point of this work is to find
out whether the edge is real, not to automate something already proven.

## Users

- **Primary**: The operator, testing CRT against futures data.
- **Not for**: Anyone else; no multi-user concerns.

## Hypothesis

We believe **coding CRT as a strategy plugin and backtesting it** will
**tell the operator whether CRT has a measurable edge** — something manual
trading cannot answer.
We'll know we're right when a backtest over real ES data produces a trade log
whose setups the operator recognises as the ones they'd have taken by hand.

## Documents

| Doc | Purpose |
|---|---|
| [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md) | The parts of the existing system CRT plugs into |
| [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) | The CRT specification itself |

## Principles

1. **Add one file; change nothing else.** CRT implements the existing
   strategy interface. If the work starts requiring edits to the engine,
   stop and re-examine.
2. **Backtest before belief.** No claim about CRT's performance until the
   backtester produces numbers.
3. **Unknowns stay labelled.** Where the strategy rules are ambiguous, the
   doc says so rather than inventing a definition.

## Known blocker

**The existing test suite has never been run here.** Only Python 3.14 is
installed, and the project pins library versions that have no Python 3.14
builds. So "the existing system works" is based on reading the code, not on
seeing tests pass.

Getting the suite green is milestone 0 — it is how we find out whether the
foundation CRT sits on is actually sound.

## Approval gate

No implementation until [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) is approved.
