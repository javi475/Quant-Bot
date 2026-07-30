# 01 — Strategy Spec: Modular Engine & Candle Range Theory (CRT)

*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Parent: [CLAUDE.md](CLAUDE.md)*

## Problem

Trading strategies evolve — the operator will want to add, disable, or A/B
test strategies over time. If CRT logic is hardwired into the execution
core, every future strategy change means touching (and risking breaking)
the order-execution and risk-management code. The operator also cannot
currently backtest CRT setups systematically or visually validate them on
TradingView, so there is no fast feedback loop for tuning the strategy.

## Evidence

- Assumption — needs validation via backtest against historical futures
  data. No live or backtested performance record exists yet for this CRT
  ruleset as specified.
- CRT setup criteria (below) are specified by the operator from strategy
  theory/notes, not from an existing coded implementation.

## Users

- **Primary**: The operator, configuring/running one or more strategies
  against live or historical futures data.
- **Not for**: Non-technical users needing a GUI strategy builder in this
  version — configuration is code/config-file based.

## Hypothesis

We believe **a strategy engine with a pluggable interface (one implementation
being CRT) plus a Python backtesting module** will **let the operator validate
and iterate on trading logic without touching execution/risk code** for
**the solo operator running prop-firm accounts**.
We'll know we're right when a new strategy can be added or CRT parameters
changed without modifying the order-routing or risk-management modules, and
when a historical backtest run produces a trade log the operator trusts
enough to decide whether to go live.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Strategy swap without core changes | 0 lines changed in execution/risk modules when adding a 2nd strategy | Code review / diff at time of 2nd strategy addition |
| Backtest reproducibility | Same input data + config → identical trade log | Re-run backtest, diff output |
| CRT detection precision | TBD — needs validation via backtest | Compare detected setups against manual chart review on a sample window |

## Scope

### MVP

- A strategy engine with a defined interface (e.g. "given OHLCV + higher
  timeframe context, return zero or more candidate setups") that the CRT
  strategy implements as its first plugin.
- CRT detection logic:
  - Locate CRT candles specifically at higher-timeframe points of interest
    (HTF supply/demand zones, previous swing highs/lows, liquidity zones).
  - Detect the manipulation phase: price sweeps liquidity above the CRT
    candle's high (or below its low) and closes back inside the range,
    forming a V-shaped reaction.
  - Two entry models, both implemented and selectable per run/config:
    - **Aggressive**: enter immediately once the V-shaped sweep is
      confirmed.
    - **Conservative**: wait for a pullback to the liquidation candle's
      demand/supply zone or a created imbalance before entering.
  - Take-profit target: the opposing end of the CRT candle's range.
  - Stop-loss: placed slightly beyond the extreme point of the
    *liquidation candle* (the actual sweep wick), not the original CRT
    candle's high/low — because the liquidation candle is the newly
    protected high/low.
- A Python-based backtesting module that parses historical OHLCV data and
  replays the CRT strategy to produce a trade log (entries, exits, R
  multiples, win rate) for operator review.
- Output of each candidate setup as a structured object/record (HTF POI,
  CRT candle, liquidation candle, entry model, proposed TP/SL) — this is
  the same structure passed downstream to the AI evaluator (see
  [03_BROKER_INTEGRATION.md](03_BROKER_INTEGRATION.md)), so strategy output
  format is a contract with that PRD.

### Out of scope

- Pine Script / TradingView export — deferred until the Python backtest and
  live detection logic are validated against real data.
- Any strategy other than CRT.
- Strategy parameter auto-optimization / machine-learned parameter tuning.
- A GUI or visual strategy configuration tool.

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Strategy engine interface | Pluggable contract exists; CRT is the sole implementation | pending | — |
| 2 | CRT detection (aggressive entry) | Detects HTF POI + sweep + V-reaction, emits aggressive-entry setups | pending | — |
| 3 | CRT detection (conservative entry) | Adds pullback-to-zone/imbalance entry as a selectable mode | pending | — |
| 4 | Python backtester | Replays historical data through the strategy, produces a trade log | pending | — |

## Open Questions

- [ ] How is "higher timeframe point of interest" (supply/demand zone,
  swing high/low, liquidity zone) defined algorithmically — manually
  annotated, or auto-detected? (Flagged as top uncertainty: **CRT signal
  detection reliability** — whether this can be coded deterministically
  without excessive false positives.)
- [ ] Which specific instrument(s) and timeframe(s) does the MVP backtest
  target first? (MVP scope says "single instrument" — which one?)
- [ ] What historical data source/vendor will feed the backtester?
- [ ] Where does the "created imbalance" (for the conservative entry) get
  defined precisely — standard fair-value-gap definition, or something
  operator-specific?

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| HTF POI detection is too subjective to automate reliably | Medium | High | Start with manually-configurable POI zones before attempting full auto-detection |
| CRT strategy has no real edge once automated | Unknown (assumption) | High | Sim-first MVP scope (per [CLAUDE.md](CLAUDE.md)) exists specifically to test this before live capital is at risk |
| Backtest data quality/gaps distort results | Medium | Medium | Validate data source coverage before trusting backtest output |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
