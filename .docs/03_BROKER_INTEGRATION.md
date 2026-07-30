# 03 — Broker Integration & AI Agentic Trade Evaluation

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md)*

## Problem

Two problems compound here. First, order execution needs a broker path that
works across multiple prop firms without per-firm custom integration code —
TradersPost webhooks are that path. Second, and more importantly: a signal
that mechanically satisfies CRT's pattern rules is not automatically a good
trade — context matters (trend, time of day, recent sweep history). Firing
blindly on every pattern match risks taking low-quality setups a human would
have skipped by "reading the room." The operator wants an LLM in the
critical path as a contextual second check, not a rubber stamp.

## Evidence

Assumption — needs validation via live/sim comparison of LLM-gated vs.
ungated trade outcomes. There is no existing data yet showing the LLM gate
improves results; this document specifies the mechanism, not a proven
benefit.

## Users

- **Primary**: The operator, whose account only ever receives orders that
  passed both the CRT strategy check and the LLM evaluator's approval.

## Hypothesis

We believe **routing every CRT-confirmed setup through an LLM evaluator
before firing a TradersPost webhook** will **filter out contextually poor
setups that pattern-matching alone would have taken** for **the solo
operator**.
We'll know we're right when, across a sample of sim trades, LLM-skipped
setups perform worse on average than LLM-approved ones — and when the
webhook payloads fired are always well-formed and accepted by TradersPost.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Webhook payload acceptance rate | 100% of fired payloads accepted (no malformed-request rejections) | TradersPost response/log review |
| LLM gate response time | TBD — needs validation (see Open Questions: LLM latency vs. futures timing) | Measured latency from setup-confirmed to LLM decision returned |
| No hardcoded-trigger execution | 0 trades fire without a corresponding LLM "EXECUTE" decision logged | Audit trail cross-check (see [04_STATE_AND_RECOVERY.md](04_STATE_AND_RECOVERY.md)) |

## Scope

### MVP

- **TradersPost webhook execution**:
  - Bot formats a JSON payload including at minimum: ticker/symbol, action
    (buy/sell), quantity, stop-loss price, take-profit price.
  - Bot fires an HTTP POST to the configured TradersPost webhook URL for
    the account/firm in use.
  - Payload construction is a single, testable function/module — not
    inlined at multiple call sites — since payload shape must stay in sync
    with whatever TradersPost currently expects.
- **AI agentic trade evaluator**:
  - When the strategy engine ([01_STRATEGY_SPEC.md](01_STRATEGY_SPEC.md))
    emits a confirmed CRT setup, and it has passed the risk gate
    ([02_PROP_FIRM_RISK.md](02_PROP_FIRM_RISK.md)), the bot packages market
    context into a JSON prompt: current trend, time of day, recent sweep
    history, and the CRT setup's variables (HTF POI, CRT candle,
    liquidation candle, entry model, proposed TP/SL).
  - This context is sent to an LLM via **OpenRouter API** (cloud, primary
    path for MVP) requesting a structured JSON response:
    `{"decision": "EXECUTE" | "SKIP", "reason": "..."}`.
  - The webhook fires **only** if `decision == "EXECUTE"`. Any other
    response, a malformed response, or a timeout is treated as `SKIP`
    (fail-closed, per [CLAUDE.md](CLAUDE.md) principle 4).
  - Every LLM request/response pair is logged for later review (ties into
    audit trail in [04_STATE_AND_RECOVERY.md](04_STATE_AND_RECOVERY.md)).

### Out of scope

- Ollama / fully local LLM inference as the primary evaluator path (may be
  added later as a fallback or cost-reduction option — see
  [CLAUDE.md](CLAUDE.md) global out-of-scope).
- Support for broker APIs other than TradersPost webhooks.
- LLM fine-tuning or prompt-optimization tooling beyond a single, reviewed
  prompt template.
- Retrying a SKIPped setup automatically — a SKIP is final for that setup
  instance.

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | TradersPost payload builder | Produces valid, TradersPost-accepted JSON from a setup + risk-sized quantity | pending | — |
| 2 | TradersPost webhook sender | Fires HTTP POST, handles response/error, logs result | pending | — |
| 3 | AI evaluator context packaging | Confirmed setup + market context serialized into evaluator prompt | pending | — |
| 4 | OpenRouter evaluator call | Sends prompt, parses structured decision, enforces fail-closed default | pending | — |
| 5 | Gate wiring | Webhook only fires on logged `EXECUTE` decision; SKIPs are traceable | pending | — |

## Open Questions

- [ ] **LLM evaluator latency vs. futures timing** (flagged as the top
  system-level uncertainty): is an LLM call in the critical path fast/
  reliable enough that the aggressive-entry model doesn't miss its window
  waiting on a response? What's the acceptable maximum latency, and what
  happens if it's exceeded — timeout-as-SKIP, or a pre-fetched/cached
  evaluation ahead of confirmation?
  This may require the conservative entry model (which has a pullback
  window) to be the only mode compatible with an LLM-gated pipeline at
  first — needs operator input once latency is measured.
- [ ] Which OpenRouter model is the default evaluator, and what's the
  fallback if OpenRouter itself is unavailable (retry, SKIP, or queue)?
- [ ] What exact TradersPost webhook URL/payload format applies per firm —
  do all four target firms integrate identically through TradersPost, or
  are there per-firm payload differences?
- [ ] Does TradersPost confirm order acceptance/fill synchronously in the
  HTTP response, or does confirmation arrive separately (relevant to
  [04_STATE_AND_RECOVERY.md](04_STATE_AND_RECOVERY.md))?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM latency causes missed or stale entries | Medium-High | High | Measure latency early in sim; consider entry-model restriction until proven acceptable |
| LLM returns malformed/unparseable JSON | Medium | Medium | Strict schema validation on response; malformed = SKIP, never best-effort parse |
| TradersPost payload spec drifts from what's coded | Low-Medium | High | Isolate payload construction in one module; validate against TradersPost docs/sandbox before each firm goes live |
| LLM evaluator becomes a rubber stamp (always EXECUTE) | Medium | Medium | Track EXECUTE/SKIP ratio and reasons in sim; treat near-100% EXECUTE rate as a signal the prompt needs revision |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
