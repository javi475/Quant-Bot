import pytest

from backend.app.services.strategy_registry import InMemoryStrategyRegistry, StrategyRegistryError
from common.enums import AssetClass

VALID_SOURCE = """
from ate_smp import StrategyBase, Signal

class MyStrategy(StrategyBase):
    def initialize(self, config):
        pass
    def on_bar(self, bar):
        return []
    def on_tick(self, tick):
        return []
    def on_fill(self, fill):
        pass
    def get_parameters_schema(self):
        return []
    def get_win_probability(self):
        return 0.55
    def get_win_loss_ratio(self):
        return 1.5
    def get_state(self):
        return {}
    def set_state(self, state):
        pass
"""

MALICIOUS_SOURCE = "import os\nfrom ate_smp import StrategyBase\nclass Bad(StrategyBase):\n    pass\n"


@pytest.fixture
def registry():
    return InMemoryStrategyRegistry()


@pytest.mark.asyncio
async def test_create_strategy(registry):
    record = await registry.create_strategy("mean-reversion-1", AssetClass.CRYPTO, ["experimental"])
    assert record.id.startswith("strat_")
    assert record.name == "mean-reversion-1"
    assert record.tags == ["experimental"]


@pytest.mark.asyncio
async def test_duplicate_name_rejected(registry):
    await registry.create_strategy("dup", AssetClass.CRYPTO)
    with pytest.raises(StrategyRegistryError):
        await registry.create_strategy("dup", AssetClass.CRYPTO)


@pytest.mark.asyncio
async def test_first_upload_auto_activates(registry):
    strategy = await registry.create_strategy("s1", AssetClass.CRYPTO)
    version = await registry.upload_version(strategy.id, VALID_SOURCE, "MyStrategy")
    assert version.version == "1.0.0"
    assert version.is_active

    active = await registry.get_active_version(strategy.id)
    assert active.id == version.id

    updated_strategy = await registry.get_strategy(strategy.id)
    assert updated_strategy.active_version_id == version.id


@pytest.mark.asyncio
async def test_second_upload_does_not_auto_activate(registry):
    strategy = await registry.create_strategy("s1", AssetClass.CRYPTO)
    v1 = await registry.upload_version(strategy.id, VALID_SOURCE, "MyStrategy")
    v2 = await registry.upload_version(strategy.id, VALID_SOURCE, "MyStrategy")

    assert v2.version == "1.0.1"  # patch bump
    assert not v2.is_active
    active = await registry.get_active_version(strategy.id)
    assert active.id == v1.id


@pytest.mark.asyncio
async def test_activate_version_switches_active_flag(registry):
    strategy = await registry.create_strategy("s1", AssetClass.CRYPTO)
    v1 = await registry.upload_version(strategy.id, VALID_SOURCE, "MyStrategy")
    v2 = await registry.upload_version(strategy.id, VALID_SOURCE, "MyStrategy")

    await registry.activate_version(strategy.id, v2.version)
    versions = await registry.list_versions(strategy.id)
    active_versions = [v for v in versions if v.is_active]
    assert len(active_versions) == 1
    assert active_versions[0].version == v2.version

    # Rollback to v1
    await registry.activate_version(strategy.id, v1.version)
    active = await registry.get_active_version(strategy.id)
    assert active.version == v1.version


@pytest.mark.asyncio
async def test_upload_rejects_sandbox_violation(registry):
    strategy = await registry.create_strategy("s1", AssetClass.CRYPTO)
    with pytest.raises(StrategyRegistryError, match="sandbox validation"):
        await registry.upload_version(strategy.id, MALICIOUS_SOURCE, "Bad")


@pytest.mark.asyncio
async def test_upload_to_unknown_strategy_rejected(registry):
    with pytest.raises(StrategyRegistryError):
        await registry.upload_version("nonexistent", VALID_SOURCE, "MyStrategy")


@pytest.mark.asyncio
async def test_activate_unknown_version_rejected(registry):
    strategy = await registry.create_strategy("s1", AssetClass.CRYPTO)
    await registry.upload_version(strategy.id, VALID_SOURCE, "MyStrategy")
    with pytest.raises(StrategyRegistryError):
        await registry.activate_version(strategy.id, "9.9.9")


@pytest.mark.asyncio
async def test_checksum_is_deterministic_sha256(registry):
    strategy = await registry.create_strategy("s1", AssetClass.CRYPTO)
    version = await registry.upload_version(strategy.id, VALID_SOURCE, "MyStrategy")
    import hashlib

    assert version.checksum_sha256 == hashlib.sha256(VALID_SOURCE.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_list_strategies(registry):
    await registry.create_strategy("s1", AssetClass.CRYPTO)
    await registry.create_strategy("s2", AssetClass.STOCKS)
    strategies = await registry.list_strategies()
    assert {s.name for s in strategies} == {"s1", "s2"}
