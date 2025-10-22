from datetime import datetime
from typing import Optional

from app.db.base import Base
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column


class UserProfile(Base):
    __tablename__ = "user_profiles"
    # TODO: Add tenant_id column and Alembic migration; enforce RLS policies in Supabase for tenant scoping

    # Supabase user id (matches auth user id)
    owner_id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)

    # Snapshot fields (from Supabase user metadata)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Preferences
    preferred_cli: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    preferred_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Activity tracking
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
