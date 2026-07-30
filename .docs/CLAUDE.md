# Quant-Bot — Project Charter

*Status: DRAFT — requirements only. No implementation until each linked PRD is approved.*

## What this is

A modular, AI-gated futures trading bot for a solo operator running prop-firm
evaluation/funded accounts. It detects Candle Range Theory (CRT) setups,
routes execution through TradersPost webhooks to a broker, and requires an
LLM "trade evaluator" to approve every signal before it fires — no trade
executes on a hardcoded trigger alone.

## Problem

The operator currently executes CRT setups manually: watching charts,
judging liquidity sweeps by eye, and placing orders by hand. This is slow,
inconsistent under fatigue/emotion, and has no automatic enforcement of
prop-firm risk rules (daily loss limits, trailing drawdown, consistency
rules) — a single manual mistake can end an evaluation or funded account.

**Evidence**: Assumption — the CRT strategy itself has not been personally
validated with a live or backtested track record yet. This system's first
job is to let the operator test the hypothesis safely (sim before live),
not to encode an already-proven edge. Treat every strategy-performance claim
in these docs as `TBD — needs validation via backtest + forward sim`.

## Why now

LLM agentic evaluation (via OpenRouter/Ollama) and broker automation (via
TradersPost webhooks) now make it feasible to insert a contextual "second
opinion" between signal detection and order execution — something a purely
mechanical algo-trading setup couldn't do before.

## Users

- **Primary**: The operator, solo, trading their own prop-firm accounts
  (Lucid Trading, Apex Trader Funding, Top One Futures, Tradeify).
- **Not for**: Other traders, teams, or multi-tenant use in this version.

## System hypothesis

We believe **a modular CRT strategy engine gated by an LLM evaluator, executing
via TradersPost** will **remove manual execution error and enforce prop-firm
risk discipline** for **the solo operator**.
We'll know we're right when a full evaluation cycle (sim, then one funded
account) runs without a manual risk-rule violation and the LLM gate
measurably blocks bad setups without materially missing good ones.

## Document map

| Doc | Covers |
|---|---|
| [01_STRATEGY_SPEC.md](01_STRATEGY_SPEC.md) | Modular strategy engine, backtesting, CRT detection & entry/exit logic |
| [02_PROP_FIRM_RISK.md](02_PROP_FIRM_RISK.md) | Prop firm rule enforcement, position sizing, drawdown/loss guardrails |
| [03_BROKER_INTEGRATION.md](03_BROKER_INTEGRATION.md) | TradersPost webhook execution, AI agentic trade evaluation |
| [04_STATE_AND_RECOVERY.md](04_STATE_AND_RECOVERY.md) | State tracking, crash recovery, webhook/fill reconciliation |

## Cross-cutting principles (apply to every PRD above)

1. **Modularity over hardcoding.** Strategies, prop-firm rule sets, and
   broker targets must be swappable configuration/plugins, not branches in
   core execution logic.
2. **No blind execution.** Every trade signal passes through the AI
   evaluator gate before a webhook fires. A gate failure or timeout defaults
   to **SKIP**, never EXECUTE.
3. **Sim before live, one firm/instrument before many.** The MVP proves the
   pipeline on one instrument and one prop firm in simulation before any
   live-money milestone is approved.
4. **Fail closed.** Any uncertainty in state (was this order filled? did the
   webhook get delivered? did the LLM respond in time?) must resolve toward
   *not* taking or *not* doubling a position.

## Global out-of-scope (this generation of docs)

- Multi-account / multi-firm concurrent orchestration.
- Additional strategies beyond CRT (the engine must support them later
  without a rewrite, but none are implemented now).
- Pine Script / TradingView export (deferred until Python backtest + live
  logic are validated).
- Fully local LLM (Ollama) path as the primary evaluator (OpenRouter cloud
  path ships first; local fallback is a later milestone).

## Approval gate

Do not begin implementation of any milestone in any linked PRD until that
PRD is explicitly approved by the operator. Use `/plan <prd-path>` per
document once approved.
