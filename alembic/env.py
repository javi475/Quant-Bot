import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.persistence.base import Base  # noqa: E402
from engine.persistence import models  # noqa: E402,F401  (registers tables on Base.metadata)

config = context.config

# Synchronous driver for Alembic's own connection (psycopg2), independent of the
# asyncpg URL the app uses at runtime.
db_url = os.environ.get(
    "DATABASE_URL_SYNC",
    os.environ.get(
        "DATABASE_URL", "postgresql+psycopg2://ate_smp:ate_smp@localhost:5432/ate_smp"
    ).replace("postgresql+asyncpg", "postgresql+psycopg2"),
)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
