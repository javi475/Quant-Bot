# 01 — CRT Strategy Specification

*Status: DRAFT — requirements only. No code until approved.*
*Parent: [CLAUDE.md](CLAUDE.md)*

This is the authoritative description of the strategy. Both the Pine Script
validation ([02_PINE_VALIDATION.md](02_PINE_VALIDATION.md)) and the eventual
Python implementation are built from this document, so they can be compared.

## Instrument and timeframe

| Setting | Value |
|---|---|
| Chart | **15 minutes** — all detection and entries |
| Holding period | **Intraday only.** Minutes to a couple of hours; never overnight |
| Trading window | **US regular session only**, hardcoded |

## The levels — computed, never drawn

At the start of each US session the bot computes four levels:

| Level | Definition |
|---|---|
| **PDH** | Prior day's high, US session only |
| **PDL** | Prior day's low, US session only |
| **ONH** | Overnight high — prior close to today's open |
| **ONL** | Overnight low — same window |

All four are active simultaneously. PDH/PDL are the heavier levels; ONH/ONL
sit closer to price and produce nearer setups.

These are arithmetic, not judgment — which is what makes the strategy
backtestable over years of history.

### Monthly higher-timeframe zones — awareness only

The operator marks weekly-scale zones about once a month. **These never
generate trades.** At most they are static context recorded alongside a
signal for review. Treating them as triggers would reintroduce the
hand-drawn discretion the computed levels exist to avoid.

---

## Two rules that govern everything

**1. Always wait for candle close.** No intrabar entries, no acting on a wick
in progress. Every decision is made on a closed 15-minute candle.

**2. Always wait for the retest.** Nothing is entered on the breaking or
sweeping candle itself. Price must return to the level and show its hand.

> The retest is the core filter. It is what removes the false signals that
> make level-based trading unprofitable, and it is why entries are never
> immediate. An earlier draft of this document specified an "aggressive"
> model that entered on the sweep close — **that model is removed.** It is
> precisely the behaviour these rules rule out.

---

## Setup A — Continuation (the level breaks and holds)

Using PDH = 5000 as the example:

1. Price trades above 5000.
2. A 15-minute candle **closes above** 5000 → the break is confirmed.
3. Price pulls back and **retests** 5000.
4. 5000 **holds as support** → **LONG**, in the direction of the breakout.

The mirror image applies below PDL/ONL for shorts.

## Setup B — Reversal (the level is swept and fails)

Same level, 5000:

1. Price wicks above 5000 but the 15-minute candle **closes back below** it.
   This is the liquidity sweep — the **liquidation candle**.
2. Price **retests** 5000 from underneath.
3. 5000 **holds as resistance** → **SHORT**, against the failed breakout.

The mirror image applies below PDL/ONL for longs.

## Both setups are live

The bot watches each level and classifies which of the two occurred. They are
different outcomes of the same interaction — a level either genuinely breaks,
or it traps people who thought it did.

---

## Stops and targets

### Target — fixed 3:1

**Every trade targets three times its stop distance.** Stop 5 points → target
15. Stop 8 points → target 24.

The stop distance is measured first, from the rules below; the target follows
from it. The point distance varies per trade, the ratio never does.

> **This supersedes an earlier rule.** The original brief specified the target
> as "the opposing end of the CRT candle's range." That is incompatible with a
> fixed 3:1 — a range-end target is whatever R the range happens to produce
> (2R on a narrow range, 4R+ on a wide one), so it cannot also always be 3R.
>
> Fixed 3:1 governs, being the operator's explicit and more recent
> instruction. **The range-end rule is worth testing as a variant** — the
> backtest can run both and compare, which is the only honest way to decide
> between them. Recorded as an experiment, not a competing rule.

### Stop — anchored to the extreme, plus a buffer

**Setup B (reversal):** beyond the **liquidation candle's extreme** — the
actual sweep wick — plus a buffer of a few points.

**Setup A (continuation):** beyond the **retest's extreme** — the low of the
pullback for a long, the high for a short — plus the same buffer.

In both cases the anchor is *where price actually reached*, not the level
itself.

> **Why the anchor matters.** A stop placed at the level, or a fixed number of
> points from it, sometimes lands inside the wick that just swept it — the
> precise spot the method exists to avoid. Anchoring to the extreme adapts to
> how far the sweep actually went; the buffer then adds protection on top.
>
> The operator's instinct to sit "5 to 10 points above to avoid liquidity
> sweeps" is right — that is the buffer. Anchoring it to the wick rather than
> the level is the correction.

### Maximum stop distance

A large sweep produces a wide stop, and therefore a 3:1 target far enough away
that price may never reach it within a single session — while this is an
intraday strategy that must be flat before the close.

**A maximum stop distance is therefore required**: if the computed stop
exceeds it, the setup is skipped rather than traded at poor odds. The value is
an open question below.

---

## Session and time rules — hardcoded

- **Entries only during the US regular session.** No pre-market, no
  post-market, no overnight.
- **Flat before the close**, with a buffer. Never carried overnight.
- **No new entries inside the closing buffer**, so a position isn't opened
  only to be force-closed minutes later.

Hard constraints in code, not tunable parameters.

> **New work for the Python side:** the codebase has **no timezone or session
> handling at all** (verified — no `ZoneInfo`, no `America/New_York`; the
> existing `session` references are database sessions). It was built for
> crypto, which never closes. US daylight-saving transitions are a
> correctness trap: session boundaries computed in fixed UTC offsets drift by
> an hour twice a year.

## Scope

### In

- Four computed levels, per session.
- Both setups: continuation and reversal.
- Candle-close-only decisions; retest required before every entry.
- Session calendar: US hours only, flat before close.

### Out

- Intrabar or immediate entries — explicitly removed.
- Monthly HTF zones as a trigger (awareness only).
- Auto-tuning parameters.
- Tick-level precision. 15-minute bars are the unit.

## Open Questions

- [ ] **How big is the buffer beyond the extreme?** The operator suggested
  5–10 points. Fixed points, ticks, or a fraction of ATR? A fixed value
  behaves differently in calm and volatile sessions.
- [ ] **What is the maximum stop distance** before a setup is skipped? Too
  tight and valid setups are discarded; too loose and 3:1 targets go unreached
  before the close.
- [ ] **Does the 3:1 target survive contact with the data?** Worth testing
  against the original range-end rule, and against a partial-exit variant.
- [ ] **What counts as a valid retest?** Must the retest candle *close* beyond
  the level, or merely touch and reject intrabar? Given rule 1, presumably a
  close — needs confirming.
- [ ] **How long does a level stay armed after the break?** If price breaks
  PDH at 10:00 and doesn't retest until 15:30, is that still the setup, or
  has it gone stale? A bar-count or time limit is probably needed.
- [ ] **How close must the retest come?** Exactly to the level, within N
  ticks, or within a fraction of ATR?
- [ ] **Can a level produce more than one trade per session?** If PDH breaks,
  holds (Setup A long), then later fails — does the bot flip to Setup B, or
  is the level spent for the day?
- [ ] **In Setup B, what exactly is the "CRT candle"** whose range defines the
  target — the candle that swept, the one before it, or the candle sitting at
  the level? The target rule depends on this.
- [ ] **What if two levels sit close together** (ONH near PDH)? One setup or
  two? The engine permits one position per instrument, so a rule is needed.
- [ ] **Which contract** — ES or MES — and how are quarterly rollovers handled
  in a continuous backtest?
- [ ] **Exact session boundaries and closing buffer.** US regular session is
  09:30–16:00 ET; how many minutes before the close do entries stop?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 3:1 targets go unreached before the forced close | **Medium** | High | Intraday strategy with a hard flat-by-close rule; measure how often targets are missed vs. time-stopped, and enforce a maximum stop distance |
| Fixed point buffer behaves badly across volatility regimes | Medium | Medium | Test a fixed-point buffer against an ATR-scaled one during validation |
| Retest rules are ambiguous and the two implementations diverge | **Medium** | High | This document is the single source; Pine and Python are both built from it and cross-checked |
| Backtest repaints and flatters the strategy | **Medium** | **High** | See [02_PINE_VALIDATION.md](02_PINE_VALIDATION.md) — repainting is the main threat to trusting the result |
| DST / session boundary bugs | Medium | High | Timezone-aware throughout; explicit tests across both transitions |
| CRT has no edge once mechanised | Unknown | High | Precisely what the validation phase measures, before the bot is built |
| Coded CRT differs from how the operator actually trades | Medium | High | Validation ends with a side-by-side review of signals against the operator's own charts |

---
*Status: DRAFT — requirements only. No code until approved.*
