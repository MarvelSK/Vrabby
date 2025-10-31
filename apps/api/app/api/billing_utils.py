import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

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
        start_credits = Decimal(settings.free_credits_on_signup or 0)
        acct = UserAccount(
            owner_id=owner_id,
            credit_balance=float(start_credits),
            plan="free",
            subscription_status="none",
        )
        db.add(acct)
        # Seed a grant transaction for visibility
        db.add(CreditTransaction(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            amount=float(start_credits),
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

        target = Decimal(settings.free_credits_on_signup or 0)
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

        current = Decimal(acct.credit_balance or 0)
        delta = max(Decimal(0), target - current)
        if delta <= 0:
            return

        new_balance = (current + delta).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        acct.credit_balance = float(new_balance)
        db.add(CreditTransaction(
            id=str(uuid.uuid4()),
            owner_id=acct.owner_id,
            amount=float(delta.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
            tx_type="grant",
            description=FREE_RENEWAL_DESC,
            created_at=datetime.utcnow()
        ))
        db.commit()
        db.refresh(acct)
    except Exception:
        # Best-effort; do not fail request flow if top-up fails
        db.rollback()


def get_balance(db: Session, owner_id: str) -> float:
    acct = ensure_user_account(db, owner_id)
    # Best-effort monthly top-up check (ensure_user_account already handles it)
    try:
        return float(acct.credit_balance or 0.0)
    except Exception:
        return 0.0


def adjust_credits(db: Session, owner_id: str, delta: float, tx_type: str, description: str | None = None) -> float:
    acct = ensure_user_account(db, owner_id)
    current = Decimal(acct.credit_balance or 0)
    change = Decimal(delta)
    new_balance = current + change
    if new_balance < 0:
        raise ValueError("Insufficient credits")
    new_balance_q = new_balance.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    acct.credit_balance = float(new_balance_q)
    db.add(CreditTransaction(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        amount=float(change.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
        tx_type=tx_type,
        description=description,
        created_at=datetime.utcnow()
    ))
    db.commit()
    db.refresh(acct)
    return acct.credit_balance


# New: calculate and charge based on token usage with markup
# Returns the charged amount (credits) after markup
# PRICES are per-token internal costs denominated in credits
# Example mapping; extend as needed
PRICES_TABLE = {
    "claude-3.5-sonnet": {"input": Decimal("0.003") / Decimal(1000), "output": Decimal("0.015") / Decimal(1000)},
    "gpt-4o": {"input": Decimal("0.005") / Decimal(1000), "output": Decimal("0.015") / Decimal(1000)},
}


def charge_for_cost(db: Session, owner_id: str, internal_cost_credits: float, description: str | None = None) -> float:
    """Charge a user for an internal cost measured in credits, applying the configured markup.

    Returns the charged user-facing amount (credits) after markup and rounding.
    """
    base = Decimal(internal_cost_credits)
    if base <= 0:
        return 0.0
    markup = Decimal(str(getattr(settings, "billing_markup", 1.4) or 1.4))
    total = (base * markup).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    adjust_credits(db, owner_id, -float(total), "usage", description or "Usage charge")
    return float(total)

def charge_for_tokens(db: Session, owner_id: str, model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in PRICES_TABLE:
        raise ValueError("Unsupported model")
    # Internal per-token rates
    rates = PRICES_TABLE[model]
    input_cost = Decimal(int(input_tokens)) * Decimal(rates["input"])  # type: ignore[index]
    output_cost = Decimal(int(output_tokens)) * Decimal(rates["output"])  # type: ignore[index]
    internal_cost = input_cost + output_cost

    # Apply configurable markup
    markup = Decimal(str(getattr(settings, "billing_markup", 1.4) or 1.4))
    total_cost = (internal_cost * markup).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # Deduct from user balance
    adjust_credits(db, owner_id, -float(total_cost), "usage", f"Prompt via {model}")
    return float(total_cost)
