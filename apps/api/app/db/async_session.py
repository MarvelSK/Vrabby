from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings


def _to_async_url(url: str) -> str:
    """Convert a sync SQLAlchemy URL to an async one for Postgres/SQLite.

    - postgresql[+psycopg2]:// -> postgresql+asyncpg://
    - sqlite:/// -> sqlite+aiosqlite:///
    - otherwise: returned unchanged (caller must ensure compatibility)
    """
    if not url:
        return url
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + url[len("postgresql+psycopg2://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///") :]
    return url


ASYNC_DATABASE_URL: str = _to_async_url(settings.database_url)

# Create async engine/session factory
# PgBouncer (transaction/statement mode) breaks server-side prepared statements.
# Disable asyncpg prepared statement cache to avoid InvalidSQLStatementNameError.
async_engine: AsyncEngine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        # SQLAlchemy asyncpg dialect expects this name
        "prepared_statement_cache_size": 0,
        # Also pass through the native asyncpg argument name for completeness
        # (ignored by SQLAlchemy if not recognized, harmless otherwise)
        "statement_cache_size": 0,
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession.

    Usage:
        async def route(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # session is closed by context manager
            pass
