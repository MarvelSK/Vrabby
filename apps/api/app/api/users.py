from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, CurrentUser
from app.api.deps_async import get_db_async
from app.services.users_service import UsersService

router = APIRouter(prefix="/api/users", tags=["users"])


class UserProfileOut(BaseModel):
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

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_cli: Optional[str] = None
    preferred_model: Optional[str] = None


class UserEvent(BaseModel):
    event: str  # e.g., "login", "heartbeat"
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None


@router.get("/me", response_model=UserProfileOut)
async def get_me(db: AsyncSession = Depends(get_db_async), current_user: CurrentUser = Depends(get_current_user)):
    owner_id: str = current_user["id"]  # type: ignore
    svc = UsersService(db)
    dto = await svc.get_me(owner_id)
    return UserProfileOut.model_validate(dto.__dict__)


@router.put("/me", response_model=UserProfileOut)
async def update_me(body: UserProfileUpdate, db: AsyncSession = Depends(get_db_async), current_user: CurrentUser = Depends(get_current_user)):
    owner_id: str = current_user["id"]  # type: ignore
    svc = UsersService(db)
    dto = await svc.update_me(
        owner_id,
        email=body.email,
        name=body.name,
        avatar_url=body.avatar_url,
        preferred_cli=body.preferred_cli,
        preferred_model=body.preferred_model,
    )
    return UserProfileOut.model_validate(dto.__dict__)


@router.post("/events")
async def record_event(body: UserEvent, db: AsyncSession = Depends(get_db_async), current_user: CurrentUser = Depends(get_current_user)):
    owner_id: str = current_user["id"]  # type: ignore
    svc = UsersService(db)
    try:
        await svc.record_event(
            owner_id,
            event=body.event,
            email=body.email,
            name=body.name,
            avatar_url=body.avatar_url,
        )
        return {"ok": True}
    except Exception as e:
        # Avoid failing the UI due to transient DB issues — log and return ok
        try:
            import logging
            logging.getLogger("app.api.users").warning("record_event failed: %s", e)
        except Exception:
            pass
        return {"ok": True, "warning": "event_not_recorded"}