import uuid
from datetime import datetime

from app.core.config import settings
from app.models.billing import UserAccount, CreditTransaction
from sqlalchemy import extract
from sqlalchemy.orm import Session

FREE_RENEWAL_DESC = "Free plan monthly renewal"


def _is_subscription_active(acct: UserAccount) -> bool:
    status = (acct.subscription_status or "").lower()
    return status in ("active", "trialing", "past_due")


def ensure_user_account(db: Session, owner_id: str) -> UserAccount:
    acct = db.query(UserAccount).filter(UserAccount.owner_id == owner_id).first()
    if acct is None:
        # Create account with FREE plan and starter credits
        acct = UserAccount(
            owner_id=owner_id,
            credit_balance=settings.free_credits_on_signup,
            plan="free",
            subscription_status="none",
        )
        db.add(acct)
        # Seed a grant transaction for visibility
        db.add(CreditTransaction(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            amount=settings.free_credits_on_signup,
            tx_type="grant",
            description="Free credits on signup",
            created_at=datetime.utcnow()
        ))
        db.commit()
        db.refresh(acct)
    else:
        # If plan is empty, default to free
        if not (acct.plan and acct.plan.strip()):
            acct.plan = "free"
            db.commit()
    # Ensure monthly free top-up if applicable
    ensure_monthly_free_topup(db, acct)
    return acct


def ensure_monthly_free_topup(db: Session, acct: UserAccount) -> None:
    """Top up free plan users to the monthly free credit target once per calendar month.
    We avoid schema changes by checking for a grant transaction with the standard description
    in the current calendar month. If none exists and the user has no active subscription,
    we add just enough credits to bring balance up to the target (no rollover beyond target).
    """
    try:
        # Only for free plan and when no active paid subscription
        if (acct.plan or "free").lower() != "free":
            return
        if _is_subscription_active(acct):
            return

        target = int(settings.free_credits_on_signup)
        if target <= 0:
            return

        now = datetime.utcnow()
        # Has a monthly renewal grant this month?
        existing = (
            db.query(CreditTransaction)
            .filter(
                CreditTransaction.owner_id == acct.owner_id,
                CreditTransaction.tx_type == "grant",
                CreditTransaction.description.contains(FREE_RENEWAL_DESC),
                extract('year', CreditTransaction.created_at) == now.year,
                extract('month', CreditTransaction.created_at) == now.month,
            )
            .first()
        )
        if existing:
            return

        current = int(acct.credit_balance or 0)
        delta = max(0, target - current)
        if delta <= 0:
            return

        acct.credit_balance = current + delta
        db.add(CreditTransaction(
            id=str(uuid.uuid4()),
            owner_id=acct.owner_id,
            amount=delta,
            tx_type="grant",
            description=FREE_RENEWAL_DESC,
            created_at=datetime.utcnow()
        ))
        db.commit()
        db.refresh(acct)
    except Exception:
        # Best-effort; do not fail request flow if top-up fails
        db.rollback()


def get_balance(db: Session, owner_id: str) -> int:
    acct = ensure_user_account(db, owner_id)
    # Best-effort monthly top-up check (ensure_user_account already handles it)
    return int(acct.credit_balance or 0)


def adjust_credits(db: Session, owner_id: str, delta: int, tx_type: str, description: str | None = None) -> int:
    acct = ensure_user_account(db, owner_id)
    new_balance = (acct.credit_balance or 0) + int(delta)
    if new_balance < 0:
        raise ValueError("Insufficient credits")
    acct.credit_balance = new_balance
    db.add(CreditTransaction(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        amount=delta,
        tx_type=tx_type,
        description=description,
        created_at=datetime.utcnow()
    ))
    db.commit()
    db.refresh(acct)
    return acct.credit_balance
