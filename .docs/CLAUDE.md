# Quant-Bot / ATE-SMP — Project Charter

*Derived from the codebase as of commit `93a776b` (2026-07-30). Requirements only — no implementation until approved.*

## Read this first

**This is not a greenfield project.** The repository contains a working
multi-asset trading system ("ATE-SMP") built across milestones M0–M6: a
sandboxed strategy SDK, a walk-forward/Monte-Carlo backtester, a 13-check
pre-trade risk pipeline, an engine core with state persistence and a
watchdog, a FastAPI dashboard backend, a React frontend, and a Hermes
orchestration agent.

The current objective is **not to rebuild it**. It is to extend it with four
capabilities so it can trade Candle Range Theory (CRT) on futures through
prop-firm accounts:

1. A CRT strategy plugin
2. A TradersPost connector (outbound order execution)
3. A prop-firm risk profile that runs *alongside* the existing Kelly engine
4. An LLM trade-evaluator gate

Everything else already exists and is reused as-is.

## A note on the original design docs

The code references design documents throughout — `DOC 2 §4`, `DOC 3 §1`,
`DOC 4 §8`, `DOC 5`. **Those documents are not in the repository.** The
`.docs/` set you are reading was re-derived by reading the source, so it
describes what the code *does*, which may differ from what those documents
originally *specified*. Where a docstring cites a DOC section, that citation
is preserved as a breadcrumb but has not been independently verified.

## Problem

The operator executes CRT setups manually — watching charts, judging
liquidity sweeps by eye, placing orders by hand. This is slow, inconsistent
under fatigue, and has no automatic enforcement of prop-firm rules (daily
loss limits, trailing drawdown, consistency rules), where a single mistake
can end an evaluation or funded account.

The existing system cannot yet do this job because it targets crypto spot
via ccxt with percentage-of-portfolio Kelly sizing — not futures contracts
under absolute-dollar prop-firm constraints.

## Evidence

Assumption — the CRT strategy has **no live or backtested track record
yet**. The first job of this work is to let the operator test that
hypothesis safely, not to encode a proven edge. Every strategy-performance
claim in these docs is `TBD — needs validation via backtest + paper phase`.

The existing infrastructure's correctness is likewise **structurally
assessed, not empirically verified** — see Open Risks below.

## Users

- **Primary**: The operator, solo, trading their own prop-firm accounts
  (Lucid Trading, Apex Trader Funding, Top One Futures, Tradeify).
- **Not for**: Other traders, teams, or multi-tenant use.

## System hypothesis

We believe **adding a CRT strategy, a TradersPost connector, a prop-firm
risk profile, and an LLM trade gate to the existing ATE-SMP engine** will
**remove manual execution error and enforce prop-firm risk discipline** for
**the solo operator**.
We'll know we're right when a full evaluation cycle (paper, then one funded
account) runs without a prop-firm rule violation, and the LLM gate
measurably blocks poor setups without materially missing good ones.

## Document map

| Doc | Covers |
|---|---|
| [00_ARCHITECTURE_ASBUILT.md](00_ARCHITECTURE_ASBUILT.md) | What already exists, re-derived from source — read before the rest |
| [01_CRT_STRATEGY.md](01_CRT_STRATEGY.md) | CRT as a `StrategyBase` plugin + Pine Script export |
| [02_PROP_FIRM_RISK.md](02_PROP_FIRM_RISK.md) | Prop-firm rule profile alongside the existing Kelly engine |
| [03_TRADERSPOST_CONNECTOR.md](03_TRADERSPOST_CONNECTOR.md) | Outbound TradersPost webhook execution as a `ConnectorBase` |
| [04_LLM_TRADE_GATE.md](04_LLM_TRADE_GATE.md) | LLM evaluator as a terminal pre-trade risk check |

## Cross-cutting principles

1. **Extend, don't fork.** New capabilities implement existing abstract
   bases (`StrategyBase`, `ConnectorBase`) and slot into the existing
   `RiskManager.check_pre_trade` pipeline. If a change requires editing
   engine core, that is a signal to re-examine the design first.
2. **No blind execution.** Every entry passes the deterministic risk checks
   *and* the LLM gate. Gate failure, timeout, or malformed response
   resolves to **reject**, never approve.
3. **Fail closed.** Any uncertainty in state — fill unknown, webhook
   undelivered, LLM unreachable — resolves toward *not* taking and *not*
   doubling a position.
4. **Paper before live.** The existing `LaunchPhase` enum
   (`PAPER → SMALL → HALF → FULL`) is the promotion path. No live capital
   until the paper phase is clean.
5. **Everything is audited.** The existing append-only decision audit trail
   records every check and its rationale. New checks — including the LLM's
   reasoning — must write to the same trail.

## Out of scope

- Multi-account / multi-firm concurrent orchestration.
- Strategies beyond CRT (the plugin system supports them; none are planned).
- Replacing the existing crypto/ccxt path — it stays and keeps working.
- Ollama / local LLM inference as the primary evaluator (OpenRouter first).

## Open risks carried across all documents

| Risk | Why it matters |
|---|---|
| **Test suite has never been run in this environment** | Only Python 3.14 is installed; deps are pinned to early-2024 versions (numpy 1.26.4, psycopg2-binary 2.9.9) with no 3.14 wheels. The "existing code works" claim is structural, not verified. Resolving this is a prerequisite to any milestone. |
| **Original design docs are missing** | Code cites DOC 1–5 that don't exist. Intent behind some decisions is unrecoverable except by reading source. |
| **CRT edge is unproven** | No track record. Paper phase exists to test this. |
| **LLM latency vs. futures timing** | An LLM call in the critical path may be too slow for the aggressive entry model. See [04_LLM_TRADE_GATE.md](04_LLM_TRADE_GATE.md). |

## Approval gate

Do not implement any milestone until its document is approved. Use
`/plan .docs/<doc>` per document once approved.
