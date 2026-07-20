"""Loads a StrategyBase subclass directly from source text, after the same
sandbox validation the subprocess worker uses (engine.strategy.worker calls
an equivalent path when loading from a file). Used by the backtest service,
which runs strategies in-process (not subprocess-isolated) for speed —
DOC 2's own open question notes backtest parallelism ("in-engine vs. worker
container") as unresolved; running backtests without subprocess/rlimit
isolation is a deliberate M5 simplification, not a security boundary for
live/paper trading (that isolation is engine.strategy.runtime.StrategyProcess,
used everywhere the Engine actually executes trades).
"""

from __future__ import annotations

import types

from engine.strategy.sandbox import validate_code


def load_class_from_source(source_code: str, class_name: str, module_name: str = "uploaded_strategy") -> type:
    validate_code(source_code)

    module = types.ModuleType(module_name)
    exec(compile(source_code, f"<{module_name}>", "exec"), module.__dict__)

    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"strategy source has no class named '{class_name}'")
    return cls
