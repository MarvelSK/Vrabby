from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profiles import UserProfile


class UsersRepository:
    """Repository for user profile persistence.

    Uses SQLAlchemy AsyncSession for non-blocking DB access.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_owner_id(self, owner_id: str) -> Optional[UserProfile]:
        result = await self.db.execute(select(UserProfile).where(UserProfile.owner_id == owner_id))
        return result.scalar_one_or_none()

    async def insert(self, profile: UserProfile) -> UserProfile:
        self.db.add(profile)
        await self.db.flush()
        return profile

    async def save(self, profile: UserProfile) -> UserProfile:
        # SQLAlchemy tracks changes; flush ensures SQL side effects before commit
        await self.db.flush()
        return profile
