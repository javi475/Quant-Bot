# Quant-Bot — Project Charter

*Current scope: the CRT strategy, backtested. Requirements only — no code until approved.*

## The short version

This repository already contains a working trading system called **ATE-SMP**
(~216 files: strategy runtime, backtester, risk manager, dashboard, test
suite), built by earlier work in this repo.

It does **not** contain a Candle Range Theory strategy.

**Current goal: write CRT as one strategy plugin, and backtest it.** The
machine to run it already exists.

## The end state, and where we are on the way there

The operator's actual goal is a bot that **runs autonomously on a VPS**,
trades the US session without supervision, and produces end-of-day stats to
review. The operator is at the desk for the open regardless — the bot exists
to remove the failure point that discretion introduces: **human emotion**.

That is a two-phase job, and the phases must happen in this order:

| Phase | What | Status |
|---|---|---|
| **1. Does it work?** | Code CRT, backtest it over real 15m data | **Current scope** |
| **2. Make it trade** | Broker execution, live risk limits, VPS deployment, daily reporting | Not started |

Phase 1 first is not bureaucracy. Automating a strategy before knowing
whether it has an edge just means losing money without emotion — faster and
more consistently than by hand. The backtest is what decides whether phase 2
is worth building.

**So: CRT is backtest-only right now.** It will not place a real order,
because nothing in current scope connects it to a broker. That is intended.

## On hosting — Pine Script isn't needed

Pine Script was considered as a way to get the bot hosted. It isn't
necessary, and it would cost more than it gives:

- The strategy would have to be **rewritten in a second language**, and the
  two versions would drift.
- Pine can't reach a broker for prop-firm futures the way this system can.
- **This repo already ships a `docker-compose.yml`** — it's built to run on
  exactly the kind of VPS the operator described.

TradingView remains useful for *looking* at charts. It isn't the runtime.

## Problem

The operator trades CRT by hand — watching for a sweep at a key level and
judging the reaction in real time. It can't be tested over history, so nobody
knows if it has an edge, and every entry is exposed to emotion in the moment.

## Evidence

Assumption — **CRT has no track record here, live or backtested.** The rules
come from how the operator actually trades. The point of this work is to find
out whether the edge is real.

## Users

- **Primary**: The operator, solo, at the desk before the opening bell.
- **Not for**: Anyone else; no multi-user concerns.

## Hypothesis

We believe **coding CRT with mechanically-computed levels and backtesting it**
will **tell the operator whether CRT has a measurable edge** — which manual
trading cannot answer.
We'll know we're right when a backtest over real 15-minute ES data produces a
trade log whose setups the operator recognises as their own.

## Documents

| Doc | Purpose |
|---|---|
| [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md) | The parts of the existing system CRT plugs into |
| [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) | The CRT specification — levels, setup, session rules |

Previously drafted and removed from scope, recoverable at commit `5e6c713`:
prop-firm risk rules, TradersPost execution, and LLM trade evaluation. Much
of that becomes phase 2 — but nothing in `.docs/` should reference them as
active work until then.

## Principles

1. **Add one file; change nothing else.** CRT implements the existing
   strategy interface. If the work starts demanding engine edits, stop and
   re-examine.
2. **Backtest before belief.** No claim about CRT's performance until the
   backtester produces numbers.
3. **Levels are computed, never drawn.** Prior-day and overnight highs/lows
   are arithmetic. Any rule requiring hand-marked zones is not automatable
   and doesn't belong in the signal path.
4. **Unknowns stay labelled.** Where the rules are ambiguous, the docs say so
   rather than inventing a definition.

## Known blockers

**1. The existing test suite has never been run here.** Only Python 3.14 is
installed, and the project pins library versions with no 3.14 builds. So "the
existing system works" is read from the code, not observed. Getting the suite
green is milestone 0.

**2. 15-minute historical data.** The existing backtest script uses yfinance,
which serves only ~60 days of 15m history — enough to prove the code runs,
not enough to prove the strategy works. A real futures data vendor is needed
before the backtest means anything.

## Approval gate

No implementation until [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) is approved.
