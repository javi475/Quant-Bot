# 02 — Prop-Firm Risk Profile

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md) · Prerequisite: [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md)*

## Problem

The existing risk engine is sound but speaks the wrong units. Every value in
`RiskConfig` is a **fraction of portfolio** — `max_drawdown: 0.15`,
`daily_loss_breaker: -0.03`, Kelly-based position sizing.

Prop firms (Lucid, Apex, Top One, Tradeify) enforce **absolute dollar**
limits: a trailing drawdown that ratchets up behind peak equity, a hard
daily-loss cap, sometimes a consistency rule capping any single day's share
of total profit. Breaching one doesn't reduce returns — it **ends the
account**.

A 15%-of-portfolio drawdown ceiling and a $2,500 trailing drawdown are not
translations of each other. They can disagree at exactly the wrong moment.

## Evidence

Assumption — needs validation against each firm's current rulebook. **No
firm-specific numeric thresholds are captured yet.** Max daily loss, trailing
drawdown amount and ratchet method, consistency percentage, minimum trading
days, and scaling rules must be sourced per firm before any config is
authored. Nothing in this document should be read as stating a firm's actual
rules.

## Users

- **Primary**: The operator, running one account at one firm in the MVP.

## Hypothesis

We believe **a prop-firm rule profile running alongside the existing
percentage/Kelly engine** will **prevent the rule violations that end
evaluations** for **the solo operator** — without disturbing the crypto path
that already works.
We'll know we're right when the pipeline blocks a trade that would have
breached a configured absolute-dollar limit, and a full paper phase
completes with zero violations.

## Design decision: alongside, not instead

Per operator decision, the prop-firm profile is **additive**:

- The existing 13 checks keep running, unchanged, for the crypto/ccxt path.
- Futures accounts additionally load a `PropFirmProfile` whose checks are
  evaluated in the same `check_pre_trade` pipeline.
- **The strictest constraint wins.** Where both models produce a size, the
  smaller is used. Neither can loosen the other.
- Prop-firm checks are placed **early** (adjacent to the existing
  `daily_loss_breaker` / `drawdown_ceiling` checks at positions 3–4) so an
  account-ending condition short-circuits before expensive work — notably
  before the LLM call in [04_LLM_TRADE_GATE.md](04_LLM_TRADE_GATE.md).

This preserves the existing rule that **exits are never blocked**. A
prop-firm limit must never prevent closing a position — being unable to exit
is how a breach becomes a catastrophe.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Rule violations during paper phase | 0 | Decision audit trail vs. configured rules |
| Bot-computed drawdown vs. firm dashboard | Agreement within one tick | Manual reconciliation during paper phase |
| New firm onboarding | Config-only, no code change | Diff review when the 2nd firm is added |
| Existing crypto tests | Still green | Full suite after the profile lands |

## Scope

### MVP

**`PropFirmProfile` configuration** — data, not code — per firm/account:

- Account size and starting balance
- Maximum daily loss (absolute dollars)
- Trailing drawdown amount **and ratchet method** (intraday vs. end-of-day;
  whether it stops trailing at initial balance)
- Consistency rule parameters, if the firm has one
- Maximum position size / contracts per instrument
- Permitted trading hours and news-blackout windows, if enforced

**New pre-trade checks**, each emitting the standard
`RiskCheckResult(name, passed, detail)` into the existing audit trail:

- `prop_firm_daily_loss` — projected worst case (realized + open risk at
  stop) against the daily cap
- `prop_firm_trailing_drawdown` — current equity against the trailing
  threshold, computed by the firm's ratchet method
- `prop_firm_consistency` — whether this trade could breach the profit-
  distribution rule
- `prop_firm_position_limit` — contracts against the firm cap

**Contract-based position sizing** for futures: derive contract quantity from
the CRT stop distance (from `Signal.metadata`) and the per-trade dollar risk,
capped by the firm's position limit. Futures are integer contracts with
per-tick dollar values — fractional Kelly sizing does not apply cleanly.

**Equity tracking** extended to record peak equity and the trailing threshold
across restarts, persisted via the existing state/persistence layer.

**Risk events**: emit the already-defined `PROP_FIRM_RULE_WARNING` and
`PROP_FIRM_RULE_VIOLATION` (`common/enums.py`) through the existing Telegram
alerting path.

Configure **one firm only** for the MVP.

### Out of scope

- Concurrent multi-firm/multi-account rule sets.
- Automated firm rule-change detection — configs are maintained by hand.
- Replacing Kelly sizing for the crypto path.
- Payout, scaling-plan, or tax logic.

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | `PropFirmProfile` schema + validation | Firm rules expressed as validated data, mirroring the `RANGES` pattern | pending | — |
| 2 | Equity/peak/trailing tracker | Correct absolute-dollar drawdown, surviving restart | pending | — |
| 3 | Prop-firm checks in the pipeline | Four new checks, audited, short-circuiting early | pending | — |
| 4 | Contract-based sizing | Integer contracts from stop distance, strictest-wins vs. Kelly | pending | — |

## Open Questions

- [ ] Which firm and account tier is the MVP target, and what are its exact
  numeric thresholds?
- [ ] **How does each firm ratchet the trailing drawdown** — intraday high
  vs. end-of-day close, and does it stop trailing at the initial balance?
  This single answer changes the tracker's core computation.
- [ ] Does the consistency rule need historical profit distribution across
  the whole evaluation, and over what window?
- [ ] On a breach, does the bot halt entries for the day, flatten open
  positions, or halt entirely until the operator intervenes?
- [ ] Should daily-loss projection include *open* position risk-at-stop, or
  only realized P&L? Including it is more conservative and probably correct —
  needs confirmation.
- [ ] Where does per-instrument tick value and margin live — the connector's
  `get_fee_schedule`, or new instrument metadata?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Firm rules mis-transcribed into config | Medium | **Critical — account loss** | Operator sign-off on each firm's config against the live rulebook before enabling; treat as a release gate |
| Bot's drawdown math diverges from the firm's | Medium | **Critical** | Reconcile against the firm dashboard daily through the paper and SMALL phases before trusting it |
| Percentage and absolute models disagree | Medium | High | Strictest-wins is explicit and tested, not incidental |
| Adding checks destabilises the crypto path | Low-Medium | Medium | Prop-firm checks are inert unless a profile is loaded; full suite must stay green |
| A prop-firm check blocks an exit | Low | **Critical** | Follow the existing convention — entry-only checks, exits always permitted |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
