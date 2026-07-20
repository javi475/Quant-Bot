"""Strategy upload, versioning, and activation (DOC 3 §3, US-001/US-002).
Every upload is validated through the same sandbox the Engine's subprocess
runtime uses (engine.strategy.sandbox) before it's ever stored — a strategy
that would be rejected at load time is rejected here first, at upload time.

Kept as a Protocol + InMemoryStrategyRegistry, same pattern as
engine.core.repository.TradeRepository: a Postgres-backed implementation
would persist into the existing strategies/strategy_versions tables
(engine.persistence.models) but isn't built this session — no Docker
available to exercise it against a live database.
"""

from __future__ import annotations

import hashlib
import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol

from common.enums import AssetClass, StrategyLifecycleState
from engine.strategy.sandbox import StrategySandboxViolation, validate_code

INITIAL_VERSION = "1.0.0"


class StrategyRegistryError(Exception):
    pass


@dataclass
class StrategyVersionRecord:
    id: str
    strategy_id: str
    version: str
    source_code: str
    class_name: str
    checksum_sha256: str
    parameters: dict
    is_active: bool
    created_at: datetime


@dataclass
class StrategyRecord:
    id: str
    name: str
    asset_class: AssetClass
    tags: list[str] = field(default_factory=list)
    state: StrategyLifecycleState = StrategyLifecycleState.UPLOADED
    active_version_id: Optional[str] = None


def _bump_patch(version: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


class StrategyRegistry(Protocol):
    async def create_strategy(
        self, name: str, asset_class: AssetClass, tags: Optional[list[str]] = None
    ) -> StrategyRecord: ...

    async def upload_version(
        self, strategy_id: str, source_code: str, class_name: str, parameters: Optional[dict] = None
    ) -> StrategyVersionRecord: ...

    async def get_strategy(self, strategy_id: str) -> StrategyRecord: ...

    async def list_strategies(self) -> list[StrategyRecord]: ...

    async def list_versions(self, strategy_id: str) -> list[StrategyVersionRecord]: ...

    async def activate_version(self, strategy_id: str, version: str) -> StrategyVersionRecord: ...

    async def get_active_version(self, strategy_id: str) -> Optional[StrategyVersionRecord]: ...


class InMemoryStrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, StrategyRecord] = {}
        self._versions: dict[str, list[StrategyVersionRecord]] = {}
        self._id_counter = itertools.count(1)

    async def create_strategy(
        self, name: str, asset_class: AssetClass, tags: Optional[list[str]] = None
    ) -> StrategyRecord:
        if any(s.name == name for s in self._strategies.values()):
            raise StrategyRegistryError(f"strategy name '{name}' already exists")
        strategy_id = f"strat_{next(self._id_counter):03d}"
        record = StrategyRecord(id=strategy_id, name=name, asset_class=asset_class, tags=tags or [])
        self._strategies[strategy_id] = record
        self._versions[strategy_id] = []
        return record

    async def upload_version(
        self, strategy_id: str, source_code: str, class_name: str, parameters: Optional[dict] = None
    ) -> StrategyVersionRecord:
        if strategy_id not in self._strategies:
            raise StrategyRegistryError(f"unknown strategy_id '{strategy_id}'")

        try:
            validate_code(source_code)
        except StrategySandboxViolation as exc:
            raise StrategyRegistryError(f"strategy failed sandbox validation: {exc}") from exc

        existing = self._versions[strategy_id]
        version = INITIAL_VERSION if not existing else _bump_patch(existing[-1].version)
        checksum = hashlib.sha256(source_code.encode("utf-8")).hexdigest()

        record = StrategyVersionRecord(
            id=str(uuid.uuid4()),
            strategy_id=strategy_id,
            version=version,
            source_code=source_code,
            class_name=class_name,
            checksum_sha256=checksum,
            parameters=parameters or {},
            is_active=False,
            created_at=datetime.now(timezone.utc),
        )
        existing.append(record)

        if len(existing) == 1:
            # First version of a strategy activates automatically — every
            # subsequent upload requires an explicit activate_version() call
            # (matches US-002's "roll back to any prior version" flow, where
            # the currently-active version is always an explicit choice).
            await self.activate_version(strategy_id, version)

        return record

    async def get_strategy(self, strategy_id: str) -> StrategyRecord:
        record = self._strategies.get(strategy_id)
        if record is None:
            raise StrategyRegistryError(f"unknown strategy_id '{strategy_id}'")
        return record

    async def list_strategies(self) -> list[StrategyRecord]:
        return list(self._strategies.values())

    async def list_versions(self, strategy_id: str) -> list[StrategyVersionRecord]:
        if strategy_id not in self._versions:
            raise StrategyRegistryError(f"unknown strategy_id '{strategy_id}'")
        return list(self._versions[strategy_id])

    async def activate_version(self, strategy_id: str, version: str) -> StrategyVersionRecord:
        versions = self._versions.get(strategy_id)
        if versions is None:
            raise StrategyRegistryError(f"unknown strategy_id '{strategy_id}'")

        target = next((v for v in versions if v.version == version), None)
        if target is None:
            raise StrategyRegistryError(f"strategy '{strategy_id}' has no version '{version}'")

        for v in versions:
            v.is_active = v is target

        strategy = self._strategies[strategy_id]
        strategy.active_version_id = target.id
        strategy.state = StrategyLifecycleState.READY
        return target

    async def get_active_version(self, strategy_id: str) -> Optional[StrategyVersionRecord]:
        versions = self._versions.get(strategy_id, [])
        return next((v for v in versions if v.is_active), None)
