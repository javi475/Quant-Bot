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

## What counts as a valid retest

**The retest candle must close.** A wick that touches the zone and recovers
within the bar is not a retest. This follows the operator's history and the
candle-close rule above.

> **This is stricter than the source material, deliberately.** The CRT source
> describes the conservative entry as a *limit order* resting at the zone —
> filled the moment price mitigates it, with no wait for the bar to complete.
> Requiring a close trades some entry price for confirmation, and will
> occasionally miss trades that a limit order would have caught.
>
> That cost is the point: the retest exists to eliminate false signals, and a
> limit order fills on exactly the touch-and-fail moves the rule is meant to
> filter out.

### Where the pullback goes — an open discrepancy

The operator describes waiting for a retest **of the key level** (PDH, PDL,
ONH, ONL). The source describes something related but not identical — the
pullback destination is one of:

1. **The liquidation candle's zone** — that candle marked from high to low,
   treated as a supply zone (reversal short) or demand zone (reversal long).
   The source calls this the "extreme point of interest."
2. **The imbalance** — the gap left by the sweep candle, bounded by the prior
   candle's high and the next candle's low.

The source weighs them: price *"most of the time... tends to pull back to the
imbalance and then blast off"*, but the imbalance is the shallower entry and
price may run deeper into the extreme zone before turning.

**These are not the same as the level itself.** The liquidation candle's zone
often sits near the swept level, but the imbalance can be some distance away.

Three candidate rules, to be settled before implementation:

| Rule | Behaviour |
|---|---|
| **Level** | Retest the swept level itself (operator's description) |
| **Liquidation zone** | Retest the sweep candle's range (source's "extreme") |
| **Imbalance** | Retest the gap left by the sweep (source's preferred, shallower) |

They produce different entry prices, different stop distances, and therefore
different 3:1 targets. **This is now the most consequential undecided rule in
the strategy** — it changes what the backtest measures.

---

## Stops and targets

### Target — fixed 3:1

**Every trade targets three times its stop distance.** Stop 5 points → target
15. Stop 8 points → target 24.

The stop distance is measured first, from the rules below; the target follows
from it. The point distance varies per trade, the ratio never does.

> **An apparent conflict, resolved by the source material.** The original
> brief specified the target as "the opposing end of the CRT candle's range,"
> which cannot also always be 3R — a range-end target is whatever R the range
> happens to produce.
>
> The source document resolves it: the two rules belong to **different entry
> models**. The aggressive model targets the opposing end of the range. The
> conservative model targets a fixed R multiple — the source settles on 3R
> ("stick to three R"), while noting 4R or other multiples are equally valid
> choices.
>
> This strategy uses conservative entries. **3:1 is therefore the correct
> rule, not an override of one.** The range-end target belongs to the
> aggressive model, which is out of scope.
>
> Still worth testing as a variant during validation, since the source frames
> the multiple as a preference rather than a fixed law.

### Stop — anchored to the extreme, plus a buffer

**Setup B (reversal):** beyond the **liquidation candle's extreme** — the
actual sweep wick — plus a buffer of a few points.

**Setup A (continuation):** beyond the **retest's extreme** — the low of the
pullback for a long, the high for a short — plus the same buffer.

In both cases the anchor is *where price actually reached*, not the level
itself.

> **Why the anchor matters — and the source agrees.** The CRT source material
> is explicit: place the stop *"above the protected high, above the highest
> point of the entire liquidity sweep"*, a few points beyond it, because the
> liquidation candle's extreme is what invalidates the trade idea.
>
> It also names the failure mode of the alternative directly — traders who
> place stops at the CRT candle's high instead get *"a tiny little pullback,
> stop them out, and then later on price went in their way."*
>
> So: anchor to the extreme, never to the level. The operator's instinct to
> add breathing room "to avoid liquidity sweeps" matches the source's "few
> pips below it"; the anchor is the part worth being precise about.

**Buffer size: scaled to volatility.** A fixed point value behaves
differently on a calm morning than a volatile one — too tight when ranges
expand, needlessly wide when they contract. An ATR-derived buffer adapts.
The multiple is a parameter to settle during validation.

### Maximum stop distance

A large sweep produces a wide stop, and therefore a 3:1 target far enough away
that price may never reach it within a single session — while this is an
intraday strategy that must be flat before the close.

**A maximum stop distance is therefore required**: if the computed stop
exceeds it, the setup is skipped rather than traded at poor odds.

**The ceiling is ultimately set by the prop firm.** Every evaluation account
has a maximum drawdown that ends it, so the largest tolerable loss per trade
is a function of that account's rules — which argues for a tight ceiling.

For validation, this is a **fixed point value**, chosen conservatively. Making
it account-aware belongs to phase 3, alongside the prop-firm rule engine and
the AI evaluator the operator wants for exactly these judgement calls. Neither
is needed to answer whether the strategy has an edge, and neither exists yet.

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

- [ ] **Where does the pullback have to reach** — the level, the liquidation
  candle's zone, or the imbalance? See the discrepancy section above. **This
  is the blocking question**; the three rules measure different strategies.
- [ ] **What ATR period and multiple** define the buffer? Scaled-to-volatility
  is settled; the numbers are not.
- [ ] **What is the maximum stop distance** for validation, before the
  prop-firm-aware version exists?
- [ ] **Does mechanical CRT need a directional bias filter** to work at all?
  The source says the model is useless without one. Testable: run with and
  without an HTF trend filter and compare.
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
| **CRT may not work without directional bias** | **Medium-High** | **High** | The source states plainly that the entry model is *"absolutely useless"* without knowing how to "develop a daily bias" and identify liquidity. Our four computed levels supply the liquidity map, but **nothing currently supplies directional bias.** The backtest will reveal whether mechanical CRT stands alone; if it doesn't, a bias filter (HTF trend, premium/discount) becomes required rather than optional |
| **"A+ setups only" cannot be mechanised as stated** | **Medium** | Medium | The source insists on trading only the cleanest, most obvious setups — explicit discretion. A bot takes every setup meeting its criteria, so mechanical results will include marginal trades a human would skip, and should be expected to underperform the source's framing |
| Timeframe pairing differs from the source | Medium | Medium | The source marks ranges on 15m and drops to 5m for entries. This strategy is 15m throughout, so entries are coarser and stops likely wider. Worth testing a 15m/5m variant if 15m-only underperforms |
| Retest rules are ambiguous and the two implementations diverge | **Medium** | High | This document is the single source; Pine and Python are both built from it and cross-checked |
| Backtest repaints and flatters the strategy | **Medium** | **High** | See [02_PINE_VALIDATION.md](02_PINE_VALIDATION.md) — repainting is the main threat to trusting the result |
| DST / session boundary bugs | Medium | High | Timezone-aware throughout; explicit tests across both transitions |
| CRT has no edge once mechanised | Unknown | High | Precisely what the validation phase measures, before the bot is built |
| Coded CRT differs from how the operator actually trades | Medium | High | Validation ends with a side-by-side review of signals against the operator's own charts |

---
*Status: DRAFT — requirements only. No code until approved.*
