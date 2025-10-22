from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.api.auth import get_current_user, CurrentUser
from app.api.billing_utils import ensure_user_account, get_balance, adjust_credits
from app.core.config import settings
import stripe
import uuid
from app.models.billing import CreditTransaction

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    # Optional; use server defaults if omitted
    mode: str | None = None  # "subscription" or "payment"
    # quantity for credit purchases (units of credits pack)
    quantity: int | None = None
    # success/cancel URLs (frontend)
    success_url: str | None = None
    cancel_url: str | None = None


@router.get("/credits")
def get_credits(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    """Return current user's credit balance, limits and subscription status."""
    from datetime import datetime, timezone
    acct = ensure_user_account(db, current_user["id"])  # type: ignore

    # Compute next monthly reset date for FREE plan (UTC)
    next_reset_iso = None
    if (acct.plan or "free").lower() == "free" and not (acct.subscription_status or "").lower() in ("active", "trialing", "past_due"):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        year = now.year + (1 if now.month == 12 else 0)
        month = 1 if now.month == 12 else (now.month + 1)
        next_reset_iso = datetime(year, month, 1, tzinfo=timezone.utc).isoformat()

    return {
        "owner_id": acct.owner_id,
        "credit_balance": acct.credit_balance,
        "subscription_status": acct.subscription_status,
        "plan": acct.plan,
        "period_limit": settings.subscription_credits_per_period,
        "free_credits_on_signup": settings.free_credits_on_signup,
        "tokens_per_credit": settings.tokens_per_credit,
        "next_reset": next_reset_iso,
    }


@router.post("/create-checkout-session")
def create_checkout_session(body: CheckoutRequest, request: Request, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    stripe.api_key = settings.stripe_secret_key

    acct = ensure_user_account(db, current_user["id"])  # type: ignore

    # Ensure customer
    customer_id = acct.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            metadata={"owner_id": acct.owner_id}
        )
        customer_id = customer["id"]
        acct.stripe_customer_id = customer_id
        db.commit()

    success_url = body.success_url or (request.headers.get("origin", "http://localhost:3000") + "/billing/success")
    cancel_url = body.cancel_url or (request.headers.get("origin", "http://localhost:3000") + "/billing/cancel")

    mode = body.mode or ("subscription" if settings.stripe_price_sub_monthly else "payment")

    if mode == "subscription":
        if not settings.stripe_price_sub_monthly:
            raise HTTPException(status_code=400, detail="Subscription price not configured")
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": settings.stripe_price_sub_monthly, "quantity": 1}],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
        )
        return {"id": session["id"], "url": session["url"]}

    # payment (one-time credits purchase)
    if not settings.stripe_price_credits:
        raise HTTPException(status_code=400, detail="Credits price not configured")
    qty = max(1, int(body.quantity or 1))
    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        line_items=[{"price": settings.stripe_price_credits, "quantity": qty}],
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
    )
    return {"id": session["id"], "url": session["url"]}


class PortalRequest(BaseModel):
    return_url: str | None = None


@router.post("/create-portal-session")
def create_portal_session(body: PortalRequest, request: Request, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    stripe.api_key = settings.stripe_secret_key

    acct = ensure_user_account(db, current_user["id"])  # type: ignore
    if not acct.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found")

    return_url = body.return_url or request.headers.get("origin", "http://localhost:3000")
    portal = stripe.billing_portal.Session.create(customer=acct.stripe_customer_id, return_url=return_url)
    return {"url": portal["url"]}


# Stripe webhook: add credits on successful payment or invoice
@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    stripe.api_key = settings.stripe_secret_key

    payload = await request.body()
    sig = request.headers.get('stripe-signature')

    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid webhook: {e}")
    else:
        # Unsafe fallback (dev): parse without verification
        try:
            event = stripe.Event.construct_from(request.json(), stripe.api_key)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = event.get("type")

    # Handle checkout.session.completed (payment or subscription)
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        mode = session.get("mode")
        # Lookup user by customer id
        acct = db.query(
            __import__('app.models.billing', fromlist=['UserAccount']).UserAccount
        ).filter_by(stripe_customer_id=customer_id).first()
        if acct:
            if mode == "payment":
                qty = 1
                try:
                    line_items = stripe.checkout.Session.list_line_items(session["id"])  # type: ignore
                    if line_items and line_items.data:
                        qty = max(1, int(line_items.data[0].get("quantity") or 1))
                except Exception:
                    pass
                credits = settings.purchase_credits_per_unit * qty
                adjust_credits(db, acct.owner_id, credits, "purchase", "Stripe payment")
            elif mode == "subscription":
                # Initial subscription; add period credits
                adjust_credits(db, acct.owner_id, settings.subscription_credits_per_period, "purchase", "Stripe subscription start")
                acct.subscription_status = "active"
                db.commit()
    elif event_type in ("invoice.paid",):
        invoice = event["data"]["object"]
        customer_id = invoice.get("customer")
        acct = db.query(
            __import__('app.models.billing', fromlist=['UserAccount']).UserAccount
        ).filter_by(stripe_customer_id=customer_id).first()
        if acct:
            adjust_credits(db, acct.owner_id, settings.subscription_credits_per_period, "purchase", "Stripe invoice paid")
            acct.subscription_status = "active"
            db.commit()
    elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        acct = db.query(
            __import__('app.models.billing', fromlist=['UserAccount']).UserAccount
        ).filter_by(stripe_customer_id=customer_id).first()
        if acct:
            acct.subscription_status = "canceled"
            db.commit()

    return {"received": True}

@router.get("/transactions")
def list_transactions(limit: int = 50, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    """List recent credit transactions for the current user."""
    try:
        lim = max(1, min(int(limit), 200))
    except Exception:
        lim = 50
    rows = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.owner_id == current_user["id"])  # type: ignore
        .order_by(CreditTransaction.created_at.desc())
        .limit(lim)
        .all()
    )
    return [
        {
            "id": r.id,
            "amount": r.amount,
            "tx_type": r.tx_type,
            "description": r.description,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
