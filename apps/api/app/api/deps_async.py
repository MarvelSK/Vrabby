from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_session import get_async_db as get_db_async  # re-export for clarity

# Export type for FastAPI dependency annotations
AsyncSessionT = AsyncSession

__all__ = [
    "get_db_async",
    "AsyncSessionT",
]
