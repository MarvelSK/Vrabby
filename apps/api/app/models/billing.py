from datetime import datetime

from app.db.base import Base
from sqlalchemy import String, DateTime, Text, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column


class UserAccount(Base):
    __tablename__ = "user_accounts"
    # TODO: Add tenant_id column and corresponding Alembic migration; implement RLS policies for tenant isolation in Supabase

    # Supabase user id
    owner_id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)

    # Stripe linkage
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    subscription_status: Mapped[str | None] = mapped_column(String(32),
                                                            nullable=True)  # active, trialing, past_due, canceled, none
    plan: Mapped[str | None] = mapped_column(String(64), nullable=True)  # free, pro, team, enterprise

    # Credits
    credit_balance: Mapped[float] = mapped_column(Numeric(12, 6), default=0, nullable=False)

    # Audit
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                                                 nullable=False)


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)

    amount: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)  # positive for add, negative for spend/refund
    tx_type: Mapped[str] = mapped_column(String(16), nullable=False)  # purchase, spend, refund, grant
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
