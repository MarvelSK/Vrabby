from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import UserAccount


class BillingRepository:
    """Read-only repository for billing account data used by user profile enrichment."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_account(self, owner_id: str) -> Optional[UserAccount]:
        result = await self.db.execute(select(UserAccount).where(UserAccount.owner_id == owner_id))
        return result.scalar_one_or_none()
