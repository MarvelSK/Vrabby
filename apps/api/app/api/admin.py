from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path
import json
from pydantic import BaseModel

from app.api.deps import get_db
from app.api.auth import get_current_user, CurrentUser
from app.core.config import PROJECT_ROOT
from app.api.billing_utils import adjust_credits, ensure_user_account

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _is_admin(db: Session, owner_id: str) -> bool:
    try:
        from app.models.billing import UserAccount  # type: ignore
        acct = db.query(UserAccount).filter(UserAccount.owner_id == owner_id).first()
        if not acct:
            return False
        plan = (acct.plan or "").lower()
        return plan == "admin"
    except Exception:
        return False


def _require_admin(db: Session, current_user: CurrentUser) -> None:
    if not _is_admin(db, current_user["id"]):  # type: ignore
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/me")
def admin_me(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    return {"is_admin": _is_admin(db, current_user["id"]) }  # type: ignore


@router.get("/users")
def list_users(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _require_admin(db, current_user)
    try:
        from app.models.billing import UserAccount  # type: ignore
        rows = db.query(UserAccount).order_by(UserAccount.updated_at.desc()).limit(200).all()
        return [
            {
                "owner_id": r.owner_id,
                "plan": r.plan,
                "subscription_status": r.subscription_status,
                "credit_balance": float(getattr(r, "credit_balance", 0.0) or 0.0),
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AdjustCreditsBody(BaseModel):
    delta: Optional[float] = None
    set_to: Optional[float] = None


@router.post("/users/{owner_id}/credits")
def admin_adjust_credits(owner_id: str, body: AdjustCreditsBody, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _require_admin(db, current_user)
    # Ensure account exists
    ensure_user_account(db, owner_id)
    if body.set_to is not None:
        # Compute delta
        from app.models.billing import UserAccount  # type: ignore
        acct = db.query(UserAccount).filter(UserAccount.owner_id == owner_id).first()
        if not acct:
            raise HTTPException(status_code=404, detail="User account not found")
        target = float(body.set_to)
        delta = target - float(acct.credit_balance or 0.0)
    else:
        delta = float(body.delta or 0.0)
    new_balance = adjust_credits(db, owner_id, delta, "grant", "Admin adjustment")
    return {"owner_id": owner_id, "credit_balance": float(new_balance)}


class SetPlanBody(BaseModel):
    plan: Optional[str] = None
    subscription_status: Optional[str] = None


@router.post("/users/{owner_id}/plan")
def admin_set_plan(owner_id: str, body: SetPlanBody, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _require_admin(db, current_user)
    try:
        from app.models.billing import UserAccount  # type: ignore
        acct = db.query(UserAccount).filter(UserAccount.owner_id == owner_id).first()
        if not acct:
            acct = ensure_user_account(db, owner_id)
        acct.plan = body.plan or acct.plan
        if body.subscription_status is not None:
            acct.subscription_status = body.subscription_status
        db.commit()
        return {"owner_id": owner_id, "plan": acct.plan, "subscription_status": acct.subscription_status}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
def admin_projects(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _require_admin(db, current_user)
    try:
        from app.models.projects import Project  # type: ignore
        rows = db.query(Project).order_by(Project.created_at.desc()).limit(200).all()
        return [
            {
                "id": r.id,
                "name": getattr(r, "name", None),
                "owner_id": r.owner_id,
                "created_at": getattr(r, "created_at", None).isoformat() if getattr(r, "created_at", None) else None,
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}")
def admin_delete_project(project_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _require_admin(db, current_user)
    try:
        from app.models.messages import Message  # type: ignore
        from app.models.sessions import Session as ChatSession  # type: ignore
        from app.models.projects import Project  # type: ignore
        # Cascade delete related rows then the project
        db.query(Message).filter(Message.project_id == project_id).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.project_id == project_id).delete(synchronize_session=False)
        deleted = db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.commit()
        return {"deleted": deleted}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


SEO_FILE = Path(PROJECT_ROOT) / "data" / "admin_seo.json"


def _read_seo() -> dict:
    try:
        if SEO_FILE.exists():
            return json.loads(SEO_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"title": "", "description": "", "keywords": []}


def _write_seo(data: dict) -> None:
    SEO_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/seo")
def get_seo(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _require_admin(db, current_user)
    return _read_seo()


@router.put("/seo")
def put_seo(body: dict, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    _require_admin(db, current_user)
    try:
        data = _read_seo()
        data.update(body or {})
        _write_seo(data)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
