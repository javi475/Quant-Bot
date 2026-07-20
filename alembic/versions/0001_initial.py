"""Initial schema: all DOC 2 SS2.8 tables + strategy_state_log

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "strategy_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("source_code", sa.Text, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("parameters_schema", JSONB, server_default="{}"),
        sa.Column("parameters", JSONB, server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )

    op.create_table(
        "strategies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("state", sa.String(32), nullable=False, server_default="uploaded"),
        sa.Column(
            "active_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("strategy_versions.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_foreign_key(
        "fk_strategy_versions_strategy_id",
        "strategy_versions",
        "strategies",
        ["strategy_id"],
        ["id"],
    )

    op.create_table(
        "strategy_state_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_id", UUID(as_uuid=True), sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("state", JSONB, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_strategy_state_log_strategy_time", "strategy_state_log", ["strategy_id", "recorded_at"]
    )

    op.create_table(
        "connectors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("connector_type", sa.String(64), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("encrypted_credentials", sa.LargeBinary, nullable=True),
        sa.Column("config", JSONB, server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "deployments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_id", UUID(as_uuid=True), sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column(
            "strategy_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("strategy_versions.id"),
            nullable=False,
        ),
        sa.Column("connector_id", UUID(as_uuid=True), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("launch_phase", sa.String(16), nullable=False, server_default="paper"),
        sa.Column("capital_allocation", sa.Float, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "trades",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "deployment_id", UUID(as_uuid=True), sa.ForeignKey("deployments.id"), nullable=False
        ),
        sa.Column("asset", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("realized_pnl", sa.Float, nullable=True),
        sa.Column("fees", sa.Float, server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, server_default="{}"),
    )
    op.create_index("ix_trades_deployment_opened", "trades", ["deployment_id", "opened_at"])

    op.create_table(
        "fills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_id", UUID(as_uuid=True), sa.ForeignKey("trades.id"), nullable=True),
        sa.Column("venue_order_id", sa.String(128), nullable=False),
        sa.Column("asset", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("fee", sa.Float, server_default="0"),
        sa.Column("is_partial", sa.Boolean, server_default="false"),
        sa.Column("filled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "backtest_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("strategy_versions.id"),
            nullable=False,
        ),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "backtest_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", UUID(as_uuid=True), sa.ForeignKey("backtest_runs.id"), nullable=False, unique=True
        ),
        sa.Column("sharpe", sa.Float, nullable=True),
        sa.Column("is_sharpe", sa.Float, nullable=True),
        sa.Column("oos_sharpe", sa.Float, nullable=True),
        sa.Column("degradation_pct", sa.Float, nullable=True),
        sa.Column("max_drawdown", sa.Float, nullable=True),
        sa.Column("win_rate", sa.Float, nullable=True),
        sa.Column("profit_factor", sa.Float, nullable=True),
        sa.Column("mc_prob_of_ruin", sa.Float, nullable=True),
        sa.Column("mc_percentiles", JSONB, nullable=True),
        sa.Column("sensitivity", JSONB, nullable=True),
        sa.Column("equity_curve", JSONB, nullable=True),
        sa.Column("trade_log", JSONB, nullable=True),
        sa.Column("regime_breakdown", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "risk_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("action_taken", sa.String(255), server_default=""),
        sa.Column("safe_mode_activated", sa.Boolean, server_default="false"),
        sa.Column("strategy_id", UUID(as_uuid=True), sa.ForeignKey("strategies.id"), nullable=True),
        sa.Column("connector_id", UUID(as_uuid=True), sa.ForeignKey("connectors.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_risk_events_occurred_at", "risk_events", ["occurred_at"])
    op.create_index("ix_risk_events_type", "risk_events", ["event_type"])
    op.create_index("ix_risk_events_severity", "risk_events", ["severity"])

    op.create_table(
        "market_data",
        sa.Column("asset", sa.String(64), primary_key=True),
        sa.Column("timeframe", sa.String(8), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.CheckConstraint("high >= low", name="ck_market_data_high_low"),
        sa.CheckConstraint("volume >= 0", name="ck_market_data_volume_nonneg"),
    )
    # Convert to a TimescaleDB hypertable partitioned on timestamp (DOC 2 SS2.8).
    op.execute(
        "SELECT create_hypertable('market_data', 'timestamp', "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_table("market_data")
    op.drop_index("ix_risk_events_severity", table_name="risk_events")
    op.drop_index("ix_risk_events_type", table_name="risk_events")
    op.drop_index("ix_risk_events_occurred_at", table_name="risk_events")
    op.drop_table("risk_events")
    op.drop_table("backtest_results")
    op.drop_table("backtest_runs")
    op.drop_table("fills")
    op.drop_index("ix_trades_deployment_opened", table_name="trades")
    op.drop_table("trades")
    op.drop_table("deployments")
    op.drop_table("connectors")
    op.drop_index("ix_strategy_state_log_strategy_time", table_name="strategy_state_log")
    op.drop_table("strategy_state_log")
    op.drop_constraint("fk_strategy_versions_strategy_id", "strategy_versions", type_="foreignkey")
    op.drop_table("strategies")
    op.drop_table("strategy_versions")
