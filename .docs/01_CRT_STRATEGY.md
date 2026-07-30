# 01 — Candle Range Theory Strategy

*Status: DRAFT — requirements only. No code until approved.*
*Parent: [CLAUDE.md](CLAUDE.md) · Read first: [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md)*

## Problem

The operator trades CRT by hand: find a key level, wait for price to sweep
liquidity past a candle's high or low, watch it snap back inside the range,
then enter. Judged by eye, in real time, at the open.

Two things are wrong with that. It can't be tested over history, so nobody
knows if it has an edge. And it runs on human emotion — the operator's stated
reason for wanting a bot at all.

## Evidence

Assumption — **no track record exists, live or backtested.** The rules below
are the operator's, transcribed from how they actually trade. This milestone
produces the first real evidence either way.

## Users

- **Primary**: The operator, who is at the desk before the opening bell and
  wants the bot making the entries instead of doing it by hand.

## Hypothesis

We believe **coding CRT with mechanically-defined levels and backtesting it**
will **show whether CRT has a measurable edge, and remove emotion from
execution**.
We'll know we're right when the backtest produces a trade log whose setups
the operator recognises as their own.

---

## Instrument and timeframe

| Setting | Value |
|---|---|
| Chart timeframe | **15 minutes** — all detection and entries |
| Holding period | **Intraday only.** Minutes to a couple of hours; never overnight |
| Trading window | **US regular session only**, hardcoded |

## The levels — mechanically defined

This is the part that makes CRT automatable. **Every level is computed from
price data. Nothing is hand-drawn.**

At the start of each US session, the bot computes four levels:

| Level | Definition |
|---|---|
| **PDH** | Prior day's high, US session only |
| **PDL** | Prior day's low, US session only |
| **ONH** | Overnight high — the session from the prior day's close to today's open |
| **ONL** | Overnight low — same window |

Both pairs are active simultaneously and work together. PDH/PDL are the
heavier levels; ONH/ONL sit closer to current price and give nearer setups.

> **Why this matters:** these are arithmetic, not judgment. The bot derives
> them the same way every day, and a backtest reproduces them exactly over
> years of history. This removes the single biggest risk previously flagged
> against automating CRT.

### Monthly higher-timeframe zones — awareness only

The operator also marks weekly-scale supply/demand zones roughly once a
month, because those levels move slowly.

**These do not generate trades.** They are context the operator keeps on the
chart for awareness. In the bot they are, at most, a static configuration
file that gets recorded alongside a signal for later review — never a trigger
or a filter.

Treating them otherwise would reintroduce exactly the hand-drawn
discretionary input that PDH/PDL/ONH/ONL avoid.

## The setup

On the 15-minute chart, at one of the four levels:

### 1. The CRT candle

A 15-minute candle forming at or against an active level. Its high and low
are the range boundaries.

### 2. The manipulation

The **next** candle — the **liquidation candle** — sweeps liquidity past the
CRT candle's high or low, then **closes back inside** the CRT candle's range.
That snap back is the V-shaped reaction.

No sweep, or a sweep that closes outside the range, is not a setup.

### 3. Entry — two selectable models

| Model | Behaviour |
|---|---|
| **Aggressive** | Enter immediately on the liquidation candle's close back inside |
| **Conservative** | Wait for a pullback into the liquidation candle's zone, or an imbalance created by the move |

### 4. Take profit

The **opposing end of the CRT candle's range**. Swept the low → target the
high, and vice versa.

### 5. Stop loss

Slightly beyond the **liquidation candle's extreme** — the actual sweep wick
— **not** the CRT candle's high or low.

This is the crux of the method: the liquidation candle is the newly protected
high/low. A stop at the CRT candle's edge sits inside territory price just
proved it will reach.

## Session and time rules — hardcoded

Non-negotiable, per the operator:

- **Entries only during the US regular session.** No pre-market, no
  post-market, no overnight.
- **Flat before the close.** Any open position is closed before the session
  ends, with a buffer — never carried overnight.
- **No new entries inside the closing buffer**, so a fresh position isn't
  opened only to be force-closed minutes later.

These are hard constraints in code, not tunable parameters.

> **New work:** the codebase has **no timezone or session handling at all**
> (verified — no `ZoneInfo`, no `America/New_York`; the existing `session`
> references are database sessions). It was built for crypto, which never
> closes. A session calendar is therefore part of this milestone, and
> **US daylight-saving transitions are a correctness trap** — a session
> boundary computed in fixed UTC offsets silently drifts by an hour twice a
> year.

## What the strategy emits

A `Signal` per setup, carrying in `metadata`: which level triggered it
(PDH/PDL/ONH/ONL), the CRT candle's high and low, the liquidation candle's
extreme, which entry model fired, and the intended stop and target.

## Kelly inputs — an honest caveat

`StrategyBase` requires `get_win_probability()` and `get_win_loss_ratio()`.

The **win/loss ratio is derivable** — target is the far end of the range,
stop is just past the sweep, so R is known per setup.

**Win probability is not.** No data exists. It returns a conservative
placeholder, clearly marked, replaced once the backtest produces a real
number. A fabricated win rate driving sizing is worse than no strategy.

## Scope

### In

- The four computed levels, per session.
- CRT detection on 15m: candle at level → sweep → close back inside.
- Both entry models, parameter-selectable.
- Stop and target per the rules above.
- Session calendar: US hours only, flat before close.
- Backtest through the existing walk-forward / Monte Carlo pipeline.

### Out

- Live or funded trading. **This milestone is backtest-only** — nothing here
  connects to a broker. Autonomous live operation is the next phase; see
  [CLAUDE.md](CLAUDE.md).
- Monthly HTF zones as a trading trigger (awareness only, above).
- Auto-tuning parameters.
- Tick-level precision — `on_tick` returns `[]`; 15m bars are the unit.

## Milestones

| # | Milestone | Outcome | Status |
|---|---|---|---|
| 0 | Green test baseline | Existing suite runs on Python 3.11/3.12 | pending |
| 1 | Session calendar + level computation | PDH/PDL/ONH/ONL computed correctly per session, DST-safe | pending |
| 2 | CRT detection, aggressive entry | Emits signals with full `metadata` on 15m bars | pending |
| 3 | Conservative entry | Pullback / imbalance entry, parameter-selectable | pending |
| 4 | Backtest on real 15m ES data | Walk-forward + Monte Carlo results the operator can judge | pending |

Milestone 1 is worth its own step: if the levels are off by a session or an
hour, every downstream result is wrong in a way that looks plausible.

## Open Questions

Fewer than before — the level definitions resolved the big one. These remain:

- [ ] **Where does 15-minute historical data come from?** This is now the
  blocking question. The existing `backtest_es_futures.py` uses yfinance,
  which only serves roughly **60 days** of 15-minute history. That is far too
  little for walk-forward analysis to mean anything. A real futures data
  vendor is needed, and it likely costs money. Options need pricing before
  milestone 4.
- [ ] **Which contract?** ES specifically, or MES (micro) — and how are
  quarterly rollovers handled in a continuous backtest?
- [ ] **Must the sweep take out the level too**, or only the CRT candle's
  high/low while merely being *near* the level? These give materially
  different trade counts.
- [ ] **How close to a level must a candle be to qualify as a CRT candle** —
  touching it, within N ticks, within an ATR fraction?
- [ ] **Exact session boundaries and the closing buffer.** US regular session
  is 09:30–16:00 ET; how many minutes before the close do entries stop and
  forced flattening begin?
- [ ] **Does the operator trade the opening bell itself**, or wait for the
  first 15m candle to complete? They are at the desk for the open, which
  suggests the former — but the first candle of the session is also the most
  volatile.
- [ ] **How far beyond the liquidation candle's extreme does the stop sit** —
  fixed ticks, ATR multiple, or tunable?
- [ ] **If two levels trigger at once** (e.g. ONH sits near PDH), is that one
  setup or two? The engine allows one position per asset, so a rule is needed.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **15m data unavailable or costly** | **High** | **High** | Price vendors before committing to milestone 4; 60 days of yfinance data is enough to prove the code works, not enough to prove the strategy does |
| DST / session boundary bugs | **Medium** | High | Timezone-aware dates throughout; explicit tests across both DST transitions |
| CRT has no edge once mechanised | Unknown | High | Precisely what this measures — and cheap to find out on paper |
| Coded CRT differs from the operator's real method | Medium | High | Milestone 2 ends with a side-by-side review of detected setups against the operator's own charts before building further |
| Placeholder win-probability mistaken for real | Medium | Medium | Marked explicitly in code; replaced with the backtested figure |
| Backtest looks good because it overfits 60 days | Medium | High | Walk-forward and Monte Carlo already exist for this; do not skip them |

---
*Status: DRAFT — requirements only. No code until approved.*
