"""Async SQLAlchemy engine/session factory, driven by DATABASE_URL (DOC 2 §2.8)."""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://ate_smp:ate_smp@localhost:5432/ate_smp"
)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
