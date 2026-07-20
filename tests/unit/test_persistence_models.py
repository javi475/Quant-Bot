"""Sanity checks that the ORM models import cleanly and register on Base.metadata
(DOC 2 §2.8). Does not require a live database."""

from engine.persistence.base import Base
from engine.persistence import models  # noqa: F401


EXPECTED_TABLES = {
    "strategies",
    "strategy_versions",
    "strategy_state_log",
    "connectors",
    "deployments",
    "trades",
    "fills",
    "backtest_runs",
    "backtest_results",
    "risk_events",
    "market_data",
    "system_settings",
}


def test_all_expected_tables_registered():
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_market_data_composite_primary_key():
    table = Base.metadata.tables["market_data"]
    pk_cols = {c.name for c in table.primary_key.columns}
    assert pk_cols == {"asset", "timeframe", "timestamp"}
