"""Host-side handle for a single strategy subprocess (DOC 2 §2.4, §5; DOC 3 §11).
The Engine's signal scheduler holds one StrategyProcess per running strategy and
talks to it exclusively through this class — it never imports strategy code.

on_bar/on_tick enforce the 5-second budget (DOC 3 §1, §11): a timeout raises
StrategyTimeoutError, which the caller (Engine) turns into "kill the process,
restart from last persisted state" per the error-handling table in DOC 3 §11.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from engine.strategy import serialization as ser
from sdk.ate_smp.models.bar import Bar, Tick
from sdk.ate_smp.models.signal import FillNotification, Signal
from sdk.ate_smp.models.strategy_config import ParameterDefinition, StrategyConfig

ON_BAR_TIMEOUT_SECONDS = 5.0
INITIALIZE_TIMEOUT_SECONDS = 10.0
DEFAULT_CALL_TIMEOUT_SECONDS = 5.0


class StrategyProcessError(Exception):
    """Base class for strategy-subprocess IPC failures."""


class StrategyTimeoutError(StrategyProcessError):
    """A call did not respond within its budget; the process should be killed."""


class StrategyCrashedError(StrategyProcessError):
    """The subprocess exited (or its stdout closed) mid-call."""


class StrategyRuntimeError(StrategyProcessError):
    """The strategy raised an exception while handling a specific call; the
    process itself is still alive and can keep serving other strategies/calls."""


class StrategyProcess:
    def __init__(self, strategy_id: str, module_path: str, class_name: str) -> None:
        self.strategy_id = strategy_id
        self.module_path = module_path
        self.class_name = class_name
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._call_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "engine.strategy.worker",
            self.module_path,
            self.class_name,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def kill(self) -> None:
        if self._process is not None and self._process.returncode is None:
            self._process.kill()
            await self._process.wait()

    async def shutdown(self, timeout: float = 5.0) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        try:
            await self._call("shutdown", {}, timeout=timeout)
        except StrategyProcessError:
            pass
        finally:
            if self._process.returncode is None:
                await self.kill()

    async def _read_stderr_tail(self, max_bytes: int = 2000) -> str:
        if self._process is None or self._process.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(self._process.stderr.read(max_bytes), timeout=1.0)
            return data.decode(errors="replace")
        except asyncio.TimeoutError:
            return ""

    async def _call(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise StrategyProcessError(f"strategy {self.strategy_id} process not started")

        async with self._call_lock:
            self._next_id += 1
            request_id = self._next_id
            request = json.dumps({"id": request_id, "method": method, "params": params}) + "\n"

            self._process.stdin.write(request.encode())
            await self._process.stdin.drain()

            try:
                line = await asyncio.wait_for(self._process.stdout.readline(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise StrategyTimeoutError(
                    f"strategy {self.strategy_id} timed out on '{method}' after {timeout}s"
                ) from exc

            if not line:
                stderr_tail = await self._read_stderr_tail()
                raise StrategyCrashedError(
                    f"strategy {self.strategy_id} process exited during '{method}': {stderr_tail}"
                )

            response = json.loads(line.decode())
            if response.get("id") != request_id:
                raise StrategyProcessError(
                    f"strategy {self.strategy_id} IPC response id mismatch "
                    f"(expected {request_id}, got {response.get('id')})"
                )
            if "error" in response:
                raise StrategyRuntimeError(
                    f"strategy {self.strategy_id} raised on '{method}': {response['error']}"
                )
            return response.get("result")

    # ----- Typed wrappers over the raw IPC calls -----

    async def initialize(self, config: StrategyConfig) -> None:
        await self._call(
            "initialize", {"config": ser.encode_config(config)}, timeout=INITIALIZE_TIMEOUT_SECONDS
        )

    async def on_bar(self, bar: Bar) -> list[Signal]:
        result = await self._call("on_bar", {"bar": ser.encode_bar(bar)}, timeout=ON_BAR_TIMEOUT_SECONDS)
        return [ser.decode_signal(s) for s in result]

    async def on_tick(self, tick: Tick) -> list[Signal]:
        result = await self._call(
            "on_tick", {"tick": ser.encode_tick(tick)}, timeout=ON_BAR_TIMEOUT_SECONDS
        )
        return [ser.decode_signal(s) for s in result]

    async def on_fill(self, fill: FillNotification) -> None:
        await self._call(
            "on_fill",
            {"fill": ser.encode_fill_notification(fill)},
            timeout=DEFAULT_CALL_TIMEOUT_SECONDS,
        )

    async def get_parameters_schema(self) -> list[ParameterDefinition]:
        result = await self._call("get_parameters_schema", {}, timeout=DEFAULT_CALL_TIMEOUT_SECONDS)
        return [ser.decode_parameter_definition(d) for d in result]

    async def get_win_probability(self) -> float:
        return await self._call("get_win_probability", {}, timeout=DEFAULT_CALL_TIMEOUT_SECONDS)

    async def get_win_loss_ratio(self) -> float:
        return await self._call("get_win_loss_ratio", {}, timeout=DEFAULT_CALL_TIMEOUT_SECONDS)

    async def get_state(self) -> dict[str, Any]:
        return await self._call("get_state", {}, timeout=DEFAULT_CALL_TIMEOUT_SECONDS)

    async def set_state(self, state: dict[str, Any]) -> None:
        await self._call("set_state", {"state": state}, timeout=DEFAULT_CALL_TIMEOUT_SECONDS)

    async def on_strategy_enabled(self) -> None:
        await self._call("on_strategy_enabled", {}, timeout=DEFAULT_CALL_TIMEOUT_SECONDS)

    async def on_strategy_disabled(self) -> None:
        await self._call("on_strategy_disabled", {}, timeout=DEFAULT_CALL_TIMEOUT_SECONDS)

    async def on_regime_change(self, old_regime: str, new_regime: str) -> None:
        await self._call(
            "on_regime_change",
            {"old_regime": old_regime, "new_regime": new_regime},
            timeout=DEFAULT_CALL_TIMEOUT_SECONDS,
        )
