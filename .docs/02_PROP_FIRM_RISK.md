# 02 — Prop Firm Rules & Risk Management

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md)*

## Problem

Prop firms (Lucid Trading, Apex Trader Funding, Top One Futures, Tradeify)
each impose account rules — daily loss limits, trailing drawdown,
consistency rules, position size caps — that, if violated, can permanently
fail an evaluation or a funded account. An automated bot that fires trades
without checking these rules first can breach them faster than a human
would ever notice, turning an execution-speed advantage into an
account-ending liability.

## Evidence

Assumption — needs validation via each prop firm's published rulebook.
Firm-specific numeric thresholds (max daily loss, trailing drawdown
amount/method, consistency rule percentage, minimum trading days, etc.) are
**not yet captured** in this document and must be sourced from each firm's
current terms before the risk engine's parameters can be finalized.

## Users

- **Primary**: The operator, running one account (one firm, one instrument)
  in the MVP, with the expectation of expanding to more firms/accounts
  later (explicitly out of scope now — see [CLAUDE.md](CLAUDE.md)).

## Hypothesis

We believe **a firm-configurable risk-rule engine that gates every trade
against that account's specific limits** will **prevent rule violations that
would end an evaluation or funded account** for **the solo operator**.
We'll know we're right when the bot blocks or resizes a trade that would
have breached a configured limit, and when a full sim run completes with
zero rule violations.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Rule violations in sim | 0 | Review of sim trade log against configured firm rules |
| Position sizing correctness | 100% of orders sized within per-trade risk cap | Automated check comparing order size against account equity/risk config |
| Time-to-configure a new firm's rules | New firm added via config only, no code change | Code review at time of 2nd firm's rules being added |

## Scope

### MVP

- A per-account risk configuration (one config per firm/account) covering,
  at minimum:
  - Maximum daily loss limit.
  - Trailing (or static, per firm) maximum drawdown.
  - Consistency rule constraints, if the firm has one (e.g. no single day's
    profit exceeding X% of total profit).
  - Maximum position size / contracts per instrument.
- A pre-trade risk check that runs **before** the AI evaluator and before
  any TradersPost webhook fires (see
  [03_BROKER_INTEGRATION.md](03_BROKER_INTEGRATION.md)): a trade that would
  breach any configured limit is blocked outright, never just "flagged."
- Position sizing logic that derives contract quantity from the strategy's
  stop-loss distance and the account's configured per-trade risk, capped by
  the firm's max position size.
- A running account-state tracker (current daily P&L, current drawdown from
  peak equity) that the risk check reads from — see
  [04_STATE_AND_RECOVERY.md](04_STATE_AND_RECOVERY.md) for how that state is
  persisted and recovered after a restart.
- Initial rule configuration for **one** firm only (whichever firm the
  operator's first MVP account is with), fully data-driven so a second
  firm's rules are a config addition, not a code change.

### Out of scope

- Simultaneously running rule sets for multiple firms/accounts (see global
  out-of-scope in [CLAUDE.md](CLAUDE.md)).
- Automated firm rule-change detection (e.g. scraping firm terms pages) —
  rule configs are entered/updated manually by the operator.
- Tax, accounting, or payout-processing logic.

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Risk config schema | Firm rules expressed as data, not code | pending | — |
| 2 | Pre-trade risk gate | Blocks any order that would breach configured limits | pending | — |
| 3 | Position sizing | Contract quantity derived from stop distance + risk cap | pending | — |
| 4 | Account state tracker | Daily P&L and drawdown tracked and available to the gate | pending | — |

## Open Questions

- [ ] Which specific firm and account tier is the MVP's first live/sim
  target, and what are that firm's exact numeric rule thresholds?
- [ ] Do any of the four target firms define trailing drawdown differently
  (e.g. end-of-day trailing vs. intraday trailing / real-time trailing)?
  This changes how the state tracker must compute "current drawdown."
- [ ] Is there a consistency rule that requires historical (not just
  same-day) profit distribution tracking, and over what lookback window?
- [ ] What should the bot do when a rule check fails mid-session — halt all
  new entries for the day, or just block the one offending trade?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Firm rule details are wrong/outdated in config | Medium | Critical (account failure) | Manual review of each firm's current rulebook before enabling live trading on that firm; treat config as the single source of truth requiring sign-off |
| Drawdown calculation method differs from firm's actual enforcement | Medium | Critical | Validate computed drawdown against firm's own dashboard during sim/early live phase before trusting the bot's numbers alone |
| Consistency rule violated by exactly the trade the strategy engine is confident about | Low-Medium | High | Risk gate is a hard block, evaluated after strategy/AI approval, before webhook fire — no exceptions |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
