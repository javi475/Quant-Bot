"""Strategy subprocess entrypoint: `python -m engine.strategy.worker <module_path>
<class_name>`. Runs inside an isolated OS process (DOC 2 §1, DOC 3 §6) — a
crash or hang here never touches the Engine or other strategies. Talks to the
host (engine/strategy/runtime.py) over JSON-Lines on stdin/stdout.

Timeouts (e.g. the 5s on_bar budget) are enforced by the host reading with a
deadline, not by this process — a hung strategy just never gets a response
and the host kills the process. Fatal exceptions during a single method call
are caught and returned as an {"error": ...} response rather than crashing
the loop, except during startup, where an import/instantiate failure is fatal
and reported once before exit(1).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any

# The strategy SDK is distributed as a standalone `ate_smp` package (DOC 3 §10:
# `pip install ate_smp-sdk`). In this repo it lives at sdk/ate_smp, so add
# sdk/ to sys.path here — the one place a strategy's own `from ate_smp import
# ...` needs to resolve — rather than requiring every strategy author to know
# the monorepo layout.
_SDK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
if _SDK_DIR not in sys.path:
    sys.path.insert(0, _SDK_DIR)

from engine.strategy import serialization as ser
from engine.strategy.sandbox import StrategySandboxViolation, apply_resource_limits, validate_code


def _load_strategy_class(module_path: str, class_name: str):
    with open(module_path, "r", encoding="utf-8") as f:
        source = f.read()

    validate_code(source)  # defense-in-depth re-validation inside the subprocess
    apply_resource_limits()

    spec = importlib.util.spec_from_file_location("uploaded_strategy", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load strategy module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"strategy module has no class named '{class_name}'")
    return cls


def _dispatch(strategy, method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        config = ser.decode_config(params["config"])
        strategy.initialize(config)
        return None
    if method == "on_bar":
        bar = ser.decode_bar(params["bar"])
        signals = strategy.on_bar(bar)
        return [ser.encode_signal(s) for s in signals]
    if method == "on_tick":
        tick = ser.decode_tick(params["tick"])
        signals = strategy.on_tick(tick)
        return [ser.encode_signal(s) for s in signals]
    if method == "on_fill":
        fill = ser.decode_fill_notification(params["fill"])
        strategy.on_fill(fill)
        return None
    if method == "get_parameters_schema":
        return [ser.encode_parameter_definition(d) for d in strategy.get_parameters_schema()]
    if method == "get_win_probability":
        return strategy.get_win_probability()
    if method == "get_win_loss_ratio":
        return strategy.get_win_loss_ratio()
    if method == "get_state":
        return strategy.get_state()
    if method == "set_state":
        strategy.set_state(params["state"])
        return None
    if method == "on_strategy_enabled":
        strategy.on_strategy_enabled()
        return None
    if method == "on_strategy_disabled":
        strategy.on_strategy_disabled()
        return None
    if method == "on_regime_change":
        strategy.on_regime_change(params["old_regime"], params["new_regime"])
        return None
    raise ValueError(f"unknown method: {method}")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m engine.strategy.worker <module_path> <class_name>", file=sys.stderr)
        return 2

    module_path, class_name = sys.argv[1], sys.argv[2]

    try:
        strategy_cls = _load_strategy_class(module_path, class_name)
        strategy = strategy_cls()
    except (StrategySandboxViolation, Exception) as exc:  # noqa: BLE001 - fatal startup error
        print(f"FATAL: strategy load failed: {exc}", file=sys.stderr, flush=True)
        return 1

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            request_id = request["id"]
            method = request["method"]
            params = request.get("params", {})
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"id": None, "error": f"malformed request: {exc}"}), flush=True)
            continue

        if method == "shutdown":
            print(json.dumps({"id": request_id, "result": None}), flush=True)
            break

        try:
            result = _dispatch(strategy, method, params)
            print(json.dumps({"id": request_id, "result": result}), flush=True)
        except Exception as exc:  # noqa: BLE001 - never let a single call crash the loop
            print(json.dumps({"id": request_id, "error": f"{type(exc).__name__}: {exc}"}), flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
