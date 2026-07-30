# 04 — State Management & Recovery

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md)*

## Problem

The bot depends on several pieces of state staying accurate: current
account P&L/drawdown (for risk gating), which setups have already been
evaluated or traded (to avoid duplicate entries), and whether a fired
webhook actually reached TradersPost and resulted in a fill. If the bot
crashes, restarts, or a webhook call fails silently, stale or missing state
can cause it to breach a risk limit it thinks it hasn't hit yet, or to
re-fire a trade that already executed.

## Evidence

Assumption — no incident has occurred yet since the system doesn't exist.
This PRD is preventative: it exists because the operator's other
requirements (risk gating, "only fire on logged EXECUTE decisions") are
only trustworthy if the underlying state is trustworthy across restarts and
network failures.

## Users

- **Primary**: The operator, who needs confidence that a bot restart or a
  flaky network call never silently doubles a position or blinds the risk
  gate to real account state.

## Hypothesis

We believe **persisting account state, setup/decision history, and order
status durably, with fail-closed recovery on restart** will **prevent
duplicate trades and risk-limit blind spots** for **the solo operator**.
We'll know we're right when a forced bot restart mid-session resumes with
correct daily P&L/drawdown and does not re-evaluate or re-fire any
already-processed setup.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| State recovery accuracy | 100% match between pre-restart and post-restart account state (P&L, drawdown, open positions) | Forced-restart test in sim |
| Duplicate trade fires | 0 | Audit log review after forced-restart tests |
| Unreconciled webhook calls | 0 left in an unknown state after a defined reconciliation window | Reconciliation job/log review |

## Scope

### MVP

- **Durable state store** (local file-based or embedded DB is sufficient
  for solo/single-account MVP) persisting:
  - Current account daily P&L and running drawdown from peak equity (read
    by the risk gate in [02_PROP_FIRM_RISK.md](02_PROP_FIRM_RISK.md)).
  - A record of every detected setup, its AI evaluator decision
    (EXECUTE/SKIP + reason), and — if EXECUTEd — the resulting webhook
    call and any confirmation received (ties to
    [03_BROKER_INTEGRATION.md](03_BROKER_INTEGRATION.md)).
  - Idempotency key or equivalent per setup instance, so the same detected
    setup can never be evaluated or fired twice.
- **Crash/restart recovery**: on startup, the bot reloads persisted state
  before evaluating any new setups, and does not double-count or re-fire
  anything already recorded as EXECUTEd.
- **Webhook failure handling**: if the HTTP POST to TradersPost fails
  (timeout, non-2xx response, connection error), the bot records the
  attempt as failed/unknown — never assumes success — and does not
  silently retry in a way that could double-fire the same order.
- **Audit trail**: every setup → risk-check → AI decision → webhook
  attempt → (if available) fill confirmation is logged as one traceable
  chain, sufficient for the operator to reconstruct "why did/didn't this
  trade happen" after the fact.

### Out of scope

- Multi-instance/distributed state (single bot process/single account
  assumption holds for MVP, consistent with global out-of-scope in
  [CLAUDE.md](CLAUDE.md)).
- Automatic retry/self-healing of failed webhook calls — failures surface
  to the operator rather than being silently retried, until reconciliation
  behavior is validated in sim.
- A UI/dashboard for browsing the audit trail (raw log/data store access is
  sufficient for MVP).

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Durable state store | Account state and setup/decision records persist across restarts | pending | — |
| 2 | Idempotent setup handling | Same setup instance never evaluated or fired twice | pending | — |
| 3 | Restart recovery | Bot resumes with correct account state, no reprocessing of prior setups | pending | — |
| 4 | Webhook failure/reconciliation handling | Failed or unconfirmed webhook calls are recorded, never silently retried or assumed successful | pending | — |

## Open Questions

- [ ] **TradersPost ↔ broker execution guarantees** (flagged as a top
  system-level uncertainty): does TradersPost provide a reliable
  fill/rejection callback or confirmation, or only an HTTP 200 for
  "webhook received"? This determines whether the bot can ever know for
  certain a trade filled, or must reconcile against the broker/firm
  platform separately.
- [ ] What is the acceptable reconciliation window before an "unknown
  status" order is escalated to the operator for manual review?
- [ ] Is a local file-based store sufficient for MVP durability
  expectations, or does the operator want a more robust embedded database
  from the start?
- [ ] Should the bot halt all new trading automatically after any
  unresolved/unknown-status order, or only after a defined threshold of
  unknowns?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| TradersPost gives no reliable fill confirmation | Medium | High | Design state model to explicitly support an "unknown/unconfirmed" order status rather than assuming binary filled/not-filled |
| State store corruption/loss on crash | Low-Medium | Critical | Use atomic writes/append-only logging for state persistence; validate recoverability in forced-crash sim tests |
| Silent duplicate fire after restart | Low-Medium | Critical | Idempotency key per setup instance checked before any evaluation or webhook call, not just before the final fire |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
