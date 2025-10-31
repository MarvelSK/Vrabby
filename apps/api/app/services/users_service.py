from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profiles import UserProfile
from app.repositories.users_repository import UsersRepository
from app.repositories.billing_repository import BillingRepository


@dataclass
class UserProfileDTO:
    owner_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_cli: Optional[str] = None
    preferred_model: Optional[str] = None
    last_login_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    plan: Optional[str] = None
    credit_balance: Optional[int] = None


class UsersService:
    """Business logic for users and profiles.

    Keeps route handlers thin and testable.
    """

    # TODO: Add async unit tests for UsersService: get_me, update_me, and record_event flows
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users_repo = UsersRepository(db)
        self.billing_repo = BillingRepository(db)

    async def get_or_create_profile(self, owner_id: str) -> UserProfile:
        now = datetime.utcnow()
        profile = await self.users_repo.get_by_owner_id(owner_id)
        if not profile:
            profile = UserProfile(owner_id=owner_id, created_at=now, updated_at=now)
            await self.users_repo.insert(profile)
            await self.db.commit()
        return profile

    async def get_me(self, owner_id: str) -> UserProfileDTO:
        profile = await self.get_or_create_profile(owner_id)
        acct = await self.billing_repo.get_account(owner_id)
        return UserProfileDTO(
            owner_id=profile.owner_id,
            email=profile.email,
            name=profile.name,
            avatar_url=profile.avatar_url,
            preferred_cli=profile.preferred_cli,
            preferred_model=profile.preferred_model,
            last_login_at=profile.last_login_at,
            last_active_at=profile.last_active_at,
            plan=acct.plan if acct else None,
            credit_balance=acct.credit_balance if acct else None,
        )

    async def update_me(
        self,
        owner_id: str,
        *,
        email: Optional[str] = None,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        preferred_cli: Optional[str] = None,
        preferred_model: Optional[str] = None,
    ) -> UserProfileDTO:
        profile = await self.get_or_create_profile(owner_id)
        if email is not None:
            profile.email = email
        if name is not None:
            profile.name = name
        if avatar_url is not None:
            profile.avatar_url = avatar_url
        if preferred_cli is not None:
            profile.preferred_cli = preferred_cli
        if preferred_model is not None:
            profile.preferred_model = preferred_model
        profile.updated_at = datetime.utcnow()
        await self.users_repo.save(profile)
        await self.db.commit()
        acct = await self.billing_repo.get_account(owner_id)
        return UserProfileDTO(
            owner_id=profile.owner_id,
            email=profile.email,
            name=profile.name,
            avatar_url=profile.avatar_url,
            preferred_cli=profile.preferred_cli,
            preferred_model=profile.preferred_model,
            last_login_at=profile.last_login_at,
            last_active_at=profile.last_active_at,
            plan=acct.plan if acct else None,
            credit_balance=acct.credit_balance if acct else None,
        )

    async def record_event(
        self,
        owner_id: str,
        *,
        event: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow()
        profile = await self.get_or_create_profile(owner_id)
        # snapshot metadata
        if email is not None:
            profile.email = email
        if name is not None:
            profile.name = name
        if avatar_url is not None:
            profile.avatar_url = avatar_url
        # update timestamps by event
        if event == "login":
            profile.last_login_at = now
            profile.last_active_at = now
        else:
            profile.last_active_at = now
        profile.updated_at = now
        await self.users_repo.save(profile)
        await self.db.commit()
