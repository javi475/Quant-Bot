# 03 — TradersPost Connector

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md) · Prerequisite: [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md)*

## Problem

The engine can only reach crypto exchanges (ccxt) and its own paper
simulator. Prop-firm futures accounts are reached through TradersPost, which
accepts JSON over an HTTPS webhook and relays to the broker.

The repo already contains `webhook/` — but it points the **wrong way**. That
module *receives* TradingView alerts and pushes them onto
`engine:signal_queue`. TradersPost requires the bot to *send* HTTP POSTs
outward. Despite the shared word "webhook", nothing in `webhook/` is
reusable here.

## Evidence

Assumption — needs validation against TradersPost's current API
documentation and a sandbox account. The payload fields named below come
from the operator's description (ticker, action, quantity, stop loss, take
profit), **not from verified vendor documentation**. Field names, auth
method, and response semantics must be confirmed before implementation.

## Users

- **Primary**: The operator, whose futures orders reach a prop-firm account
  through TradersPost.

## Hypothesis

We believe **a `TradersPostConnector` implementing the existing
`ConnectorBase`** will **let the engine trade prop-firm futures accounts
with no changes to engine core** for **the solo operator**.
We'll know we're right when the engine places, tracks, and flattens futures
positions through TradersPost using the same code paths that already drive
ccxt and paper connectors.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Payload acceptance rate | 100% (no malformed-request rejections) | TradersPost responses in the connector log |
| Engine core changes required | 0 files | Diff review at milestone completion |
| Order/position state accuracy | Engine's view matches the broker platform | Reconciliation during paper phase |
| Unresolved-status orders | 0 beyond the reconciliation window | Audit trail review |

## Scope

### MVP

Implement `TradersPostConnector(ConnectorBase)` with `connector_id` set and
`asset_class = AssetClass.FUTURES`.

**Order placement** — `place_order` builds and POSTs a JSON payload
containing at minimum ticker/symbol, action, quantity, stop loss, and take
profit, to the account's configured TradersPost webhook URL. Payload
construction lives in **one testable function**, isolated from transport, so
vendor format drift is a single-site change.

**Capabilities** — advertise accurately via `ConnectorCapabilities`:
`supports_short=True`, `supports_stop=True`, and honest values for partial
fills, leverage, and rate limits. The engine's behaviour depends on these
being truthful.

**Credentials** — webhook URL and any secret loaded from environment/secret
storage following the existing pattern. **Never committed.** `.env.example`
gains placeholder entries only.

**Failure handling** — any non-2xx, timeout, or connection error records the
order as failed/unknown, never assumes success, and never blind-retries in a
way that could double-fire. This is the `CLAUDE.md` fail-closed principle at
the connector boundary.

**Market data** — TradersPost is an execution path, not a data feed.
`get_historical_bars` / `subscribe_live_data` must either delegate to a
separate futures data source or raise clearly. **Silently returning empty
bars would starve the strategy while looking healthy** — the worst failure
mode available here.

### The bracket-order problem

CRT produces three prices at once: entry, protective stop, take-profit.
The existing `Order` dataclass models a single order with one optional
`stop_price` and no target concept, and `ExecutionManager.place_order`
expects one order in, one `Fill` out.

Three options, to be decided before implementation:

1. **Carry stop/target in `Order.metadata`** and let the connector expand
   them into the TradersPost payload. Smallest change; the engine remains
   unaware brackets exist — which also means it cannot reason about them.
2. **Extend `Order`** with optional `take_profit_price` / bracket fields.
   Honest and explicit, but touches a core contract every connector shares.
3. **Let TradersPost own bracket lifecycle entirely** — bot fires entry with
   attached SL/TP and treats the exit as broker-managed. Simplest, but the
   engine's position view can drift from reality if a broker-side stop fires
   without notifying us.

Option 1 is the least invasive; option 2 is the most correct. **This is the
single most consequential open question in this document** — it determines
whether the engine or the broker owns exit management.

### Out of scope

- Broker APIs other than TradersPost.
- Reusing or adapting the inbound `webhook/` receiver.
- Multi-account routing.
- Automatic retry of failed sends (failures surface to the operator until
  reconciliation behaviour is proven).

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Bracket-order decision | Chosen approach documented; `Order` contract settled | pending | — |
| 2 | Payload builder | Pure function producing TradersPost-valid JSON, unit tested | pending | — |
| 3 | Connector skeleton | All `ConnectorBase` methods implemented or explicitly unsupported | pending | — |
| 4 | Order placement + failure handling | Live POST against sandbox, fail-closed on every error path | pending | — |
| 5 | Position/state reconciliation | Engine's position view matches broker through a paper session | pending | — |

## Open Questions

- [ ] **Does TradersPost confirm fills, or only receipt?** If the response is
  merely "webhook accepted", the engine can never *know* a trade filled from
  the response alone and needs a separate reconciliation source. This shapes
  the whole state model.
- [ ] Exact current payload schema, auth mechanism, and rate limits —
  requires vendor docs and a sandbox account.
- [ ] Do all four prop firms integrate identically through TradersPost, or
  are there per-firm payload differences?
- [ ] How are futures symbols expressed (`ES`, `ESZ5`, `/ES`), and how do
  contract rollovers appear?
- [ ] Which of the three bracket approaches is chosen?
- [ ] What futures market-data source feeds `get_historical_bars` and live
  bars, given TradersPost is execution-only?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| No reliable fill confirmation | Medium | High | Model an explicit "unknown" order state; never collapse unknown into filled or not-filled |
| Payload schema drifts from implementation | Low-Medium | High | Single payload-builder module; verify against sandbox before each firm goes live |
| Broker-side stop fires without notifying the engine | Medium | High | Poll/reconcile positions rather than assuming the engine's view is authoritative |
| Market-data methods silently return empty | Low | **High** | Raise explicitly rather than returning `[]`; strategy starvation must be loud |
| Webhook URL/secret leaked | Low | **Critical** | Environment/secret storage only; `.env.example` carries placeholders; never logged |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
