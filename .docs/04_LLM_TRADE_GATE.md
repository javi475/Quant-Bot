# 04 — LLM Trade Evaluator Gate

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md) · Prerequisite: [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md)*

## Problem

A signal that mechanically satisfies CRT's pattern rules is not
automatically a good trade. Context matters — prevailing trend, time of day,
how much liquidity has already been swept, whether the setup sits at a stale
level. Firing on every pattern match takes setups a human would have skipped
by reading the room.

The operator's requirement is explicit: trades must not execute on hardcoded
triggers alone. An LLM sits in the path as a contextual second opinion.

The system already has an LLM component — `hermes/` — but it is an
*orchestration* agent (scheduling, memory, Telegram), not an inline
pre-trade evaluator. Its client and prompt patterns are worth reusing; its
role is not the same.

## Evidence

Assumption — needs validation by comparing gated vs. ungated outcomes on
paper. **There is no evidence yet that an LLM gate improves results.** It is
equally plausible it adds latency and rejects good trades. This document
specifies the mechanism and the measurement; it does not assert the benefit.

## Users

- **Primary**: The operator, whose account only receives orders that passed
  both deterministic risk checks and the evaluator.

## Hypothesis

We believe **an LLM evaluator as a terminal pre-trade check** will **filter
contextually poor setups that pattern-matching alone would take** for **the
solo operator**.
We'll know we're right when, across a paper sample, LLM-rejected setups
would have performed worse than approved ones — measured, not assumed.

## Design: a 14th check, placed last

The evaluator is **not** a parallel system. It becomes an additional check in
`RiskManager.check_pre_trade`, positioned **after all 13 deterministic
checks**:

```
1..13   existing deterministic checks (+ prop-firm checks from DOC 02)
14      llm_evaluation   ← only reached if everything else passed
```

Why last:

- **Cost and latency are only spent on trades that would otherwise execute.**
  A setup rejected by drawdown or position limits never triggers an LLM call.
- **It cannot loosen anything.** By construction, a check that runs last and
  can only fail the decision is incapable of overriding a risk limit. This
  preserves the existing invariant that risk parameters are human-controlled
  and the LLM may never relax them.
- **It inherits the audit trail for free.** The decision and its reasoning
  become a `RiskCheckResult(name="llm_evaluation", passed, detail=reason)` in
  the same append-only log as every other check.
- **Exits bypass it.** Consistent with the existing convention, the check is
  entry-only. An LLM must never be able to prevent closing a position.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Trades executing without a recorded EXECUTE decision | 0 | Audit trail cross-check |
| Gate latency (p50 / p99) | TBD — see Open Questions | Measured from check entry to parsed decision |
| Approve/reject ratio | Neither extreme (~100% approve = rubber stamp; ~100% reject = useless) | Audit trail distribution over the paper phase |
| Outcome separation | Rejected setups underperform approved ones | Paper-phase shadow evaluation |

## Scope

### MVP

**Context packaging** — assemble a JSON prompt from data already available
at check time: current trend, time of day/session, recent sweep history, and
the CRT variables carried in `Signal.metadata` (HTF POI, CRT candle bounds,
liquidation candle extreme, entry model, proposed stop and target).

**Provider** — OpenRouter (cloud) as the primary path, called through a
narrow client interface so a local Ollama implementation can be substituted
later without touching the risk pipeline.

**Structured response** — the model returns
`{"decision": "EXECUTE" | "SKIP", "reason": "..."}`, validated against a
strict schema.

**Fail-closed semantics** — the check passes **only** on a well-formed
`EXECUTE`. Every other outcome fails it:

| Outcome | Result |
|---|---|
| `EXECUTE`, valid schema | pass |
| `SKIP` | fail, reason recorded |
| Malformed / unparseable JSON | fail — never best-effort parse |
| Timeout | fail |
| Provider error / unreachable | fail |

**Audit** — every request and response is logged, and the decision plus
reasoning lands in the existing decision audit trail.

**Shadow mode** — the evaluator must be runnable in a mode where it records
its decision **without** blocking execution. This is how the benefit
hypothesis gets tested without the gate itself confounding the results, and
how latency is measured before it sits in the critical path.

### Out of scope

- Ollama/local inference as the primary path (interface accommodates it; not
  built first).
- Fine-tuning or automated prompt optimization.
- Letting the LLM adjust position size, stops, targets, or any risk
  parameter. **It has exactly one power: veto.**
- Re-evaluating a rejected setup — a rejection is final for that instance.
- Repurposing Hermes as the evaluator.

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Provider client + schema validation | OpenRouter call returning a validated decision, fail-closed on every error | pending | — |
| 2 | Context packaging | CRT setup + market context serialized deterministically | pending | — |
| 3 | Shadow mode | Decisions recorded without blocking; latency measured | pending | — |
| 4 | Enforcing gate | Check 14 wired in, entry-only, fully audited | pending | — |

## Open Questions

- [ ] **Is LLM latency compatible with futures entry timing?** The dominant
  question. The aggressive entry model acts immediately on the sweep close;
  a multi-second round trip may make the fill stale or missed. Possible
  outcomes: the gate is viable for both models, viable only for the
  conservative model (which has a pullback window), or must be restructured
  (e.g. pre-evaluating candidate setups before confirmation). **Shadow mode
  exists to answer this with data before the gate blocks anything.**
- [ ] Note the interaction with the existing 5-second `on_bar` budget — the
  LLM call happens in the risk pipeline, not inside the strategy, so it does
  not consume that budget. Does the engine's own loop impose a separate
  deadline that a slow LLM call would breach?
- [ ] Which OpenRouter model, and what is the fallback if OpenRouter is
  unavailable — fail-closed reject, or degrade to deterministic-only with an
  alert?
- [ ] What is the per-trade cost ceiling, and is it material at expected
  signal frequency?
- [ ] Should the prompt include recent trade outcomes (a feedback loop), or
  does that risk the model chasing recent performance?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Latency makes entries stale or missed | **Medium-High** | High | Measure in shadow mode first; restrict to the conservative entry model if needed |
| Model becomes a rubber stamp (always EXECUTE) | Medium | Medium | Track the approve/reject distribution; near-100% approval means the prompt is not doing work |
| Model rejects good trades and the operator never learns | Medium | Medium | Shadow-evaluate rejected setups' hypothetical outcomes |
| Malformed responses handled leniently | Medium | High | Strict schema validation; no salvage parsing, ever |
| Prompt-injectable content reaches the model | Low | Medium | Context is assembled from internal numeric market data only — never from external text feeds, news, or user-supplied strings |
| LLM cost scales unexpectedly | Low-Medium | Low | Gate runs last, so only otherwise-executable trades incur cost |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
