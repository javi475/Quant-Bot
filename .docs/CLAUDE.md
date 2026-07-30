# Quant-Bot — Project Charter

*Current scope: validate CRT in Pine Script. Requirements only — no code until approved.*

## The short version

The operator trades Candle Range Theory by hand and wants a bot to trade it
autonomously, because the biggest failure point in discretionary trading is
**human emotion**.

Before building that bot, one question has to be answered: **does CRT
actually have an edge?** Nobody knows — there is no track record, live or
backtested.

So the order is: prove it, then build it.

## The three phases

| Phase | What | Why this order |
|---|---|---|
| **1. Prove it** | CRT in Pine Script, backtested on TradingView | **Current scope.** Cheapest way to find out if the edge is real |
| **2. Build it** | CRT as a Python strategy in the existing engine | Only worth doing if phase 1 says yes |
| **3. Trade it** | Broker execution, risk limits, VPS, daily reporting | The autonomous bot the operator actually wants |

Automating an unproven strategy doesn't remove emotion from trading — it
removes emotion from *losing money*, faster and more consistently than doing
it by hand. Phase 1 exists so that doesn't happen.

## Why Pine Script first

Testing CRT in Python needs 15-minute ES history. The existing data path
(yfinance) gives about **60 days** — enough to prove code runs, not enough to
prove a strategy works. A proper futures data vendor costs money.

A TradingView subscription supplies that history *and* a strategy tester, for
a fee the operator would pay anyway. **The subscription is the data
purchase.** That reasoning is why phase 1 is Pine and not Python.

TradingView is the validation environment. It is **not** the runtime — phase
3 runs on a VPS, which this repo already has a `docker-compose.yml` for.

## What already exists here

This repository is **not empty**. It contains a working multi-asset trading
system, "ATE-SMP" (~216 files: strategy runtime, backtester, risk manager,
dashboard, ~50 test modules), built by earlier work in this repo.

It has everything except a CRT strategy. That matters for phase 2 — CRT will
be one plugin file against an existing interface, not a new bot. See
[00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md).

## Problem

The operator trades CRT manually: watching for a level to break or get swept,
judging the retest in real time. It can't be tested over history, so the edge
is unknown, and every entry is exposed to emotion in the moment.

## Evidence

Assumption — **CRT has no track record here.** The rules come from how the
operator actually trades. Phase 1 produces the first real evidence either way.

## Users

- **Primary**: The operator, solo, at the desk before the opening bell.
- **Not for**: Anyone else; no multi-user concerns.

## Hypothesis

We believe **implementing CRT with mechanically-computed levels and
backtesting it properly** will **tell the operator whether CRT has a
measurable edge** — which manual trading cannot answer.
We'll know we're right when the strategy tester produces a trade log whose
setups the operator recognises as their own, with statistics clear enough to
make the go/no-go call obvious.

## Documents

| Doc | Purpose |
|---|---|
| [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) | **The strategy rules — the single source of truth** |
| [02_PINE_VALIDATION.md](02_PINE_VALIDATION.md) | Phase 1: the Pine Script backtest |
| [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md) | The existing system, for phase 2 |

Both implementations — Pine now, Python later — are built from
[01_CRT_STRATEGY.md](01_CRT_STRATEGY.md), so they can be compared and drift
can be caught.

Drafted earlier and deferred to phase 3, recoverable at commit `5e6c713`:
prop-firm risk rules, TradersPost execution, LLM trade evaluation.

## Principles

1. **Prove before building.** No bot until the backtest justifies one.
2. **Levels are computed, never drawn.** Prior-day and overnight highs/lows
   are arithmetic. Any rule needing hand-marked zones doesn't belong in the
   signal path.
3. **Candle close, then retest.** No intrabar entries; nothing entered on the
   breaking candle itself. This is the strategy's core filter.
4. **One source of truth.** Strategy rules live in one document. Two
   implementations, one specification.
5. **Unknowns stay labelled.** Where rules are ambiguous, the docs say so
   rather than inventing a definition.

## Blocking gaps

**1. Setup A has no stops or targets.** The continuation setup is specified
up to the entry and no further. It cannot be coded or backtested until that's
resolved. See [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md).

**2. TradingView plan and data depth unconfirmed.** How far back 15-minute ES
history goes determines whether the sample is large enough to mean anything.

Deferred to phase 2 (not blocking now): the existing Python test suite has
never been run here — only Python 3.14 is installed and the project pins
versions with no 3.14 builds.

## Approval gate

No implementation until [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) and
[02_PINE_VALIDATION.md](02_PINE_VALIDATION.md) are approved.
