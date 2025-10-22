from datetime import datetime

from app.api.auth import get_current_user, CurrentUser
from app.api.deps import get_db
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


def _collect_user_data(db: Session, owner_id: str) -> dict:
    data: dict = {"owner_id": owner_id}

    # Import models defensively; some may not exist in all setups
    try:
        from app.models.billing import UserAccount, CreditTransaction  # type: ignore
        acct = db.query(UserAccount).filter(UserAccount.owner_id == owner_id).first()
        txs = db.query(CreditTransaction).filter(CreditTransaction.owner_id == owner_id).order_by(
            CreditTransaction.created_at.desc()).all()
        data["account"] = {
            "credit_balance": getattr(acct, "credit_balance", None) if acct else None,
            "plan": getattr(acct, "plan", None) if acct else None,
            "subscription_status": getattr(acct, "subscription_status", None) if acct else None,
            "updated_at": getattr(acct, "updated_at", None).isoformat() if acct and getattr(acct, "updated_at",
                                                                                            None) else None,
        }
        data["credit_transactions"] = [
            {
                "id": t.id,
                "amount": t.amount,
                "tx_type": t.tx_type,
                "description": t.description,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in txs
        ]
    except Exception:
        pass

    try:
        from app.models.projects import Project  # type: ignore
        projects = db.query(Project).filter(Project.owner_id == owner_id).all()
        data["projects"] = [
            {
                "id": p.id,
                "name": getattr(p, "name", None),
                "created_at": getattr(p, "created_at", None).isoformat() if getattr(p, "created_at", None) else None,
            }
            for p in projects
        ]
    except Exception:
        pass

    try:
        from app.models.sessions import Session as ChatSession  # type: ignore
        sessions = db.query(ChatSession).filter(
            ChatSession.project_id.in_([prj.get("id") for prj in data.get("projects", [])])).all() if data.get(
            "projects") else []
        data["sessions"] = [
            {
                "id": s.id,
                "project_id": s.project_id,
                "status": getattr(s, "status", None),
                "started_at": getattr(s, "started_at", None).isoformat() if getattr(s, "started_at", None) else None,
            }
            for s in sessions
        ]
    except Exception:
        pass

    try:
        from app.models.messages import Message  # type: ignore
        project_ids = [prj.get("id") for prj in data.get("projects", [])]
        msgs = db.query(Message).filter(Message.project_id.in_(project_ids)).order_by(Message.created_at.desc()).limit(
            1000).all() if project_ids else []
        data["messages"] = [
            {
                "id": m.id,
                "project_id": m.project_id,
                "role": m.role,
                "type": getattr(m, "message_type", None),
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ]
    except Exception:
        pass

    return data


@router.get("/export")
def export_data(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    data = _collect_user_data(db, current_user["id"])  # type: ignore
    headers = {
        "Content-Disposition": f"attachment; filename=export-{current_user['id']}.json",
        "Cache-Control": "no-store",
    }
    return JSONResponse(content=data, headers=headers)


@router.post("/delete")
def delete_account_and_data(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    owner_id = current_user["id"]  # type: ignore

    # Attempt to delete user-owned data. Best-effort and idempotent.
    deleted = {"projects": 0, "messages": 0, "sessions": 0, "transactions": 0, "account": 0}

    try:
        from app.models.messages import Message  # type: ignore
        from app.models.projects import Project  # type: ignore
        from app.models.sessions import Session as ChatSession  # type: ignore
        from app.models.billing import UserAccount, CreditTransaction  # type: ignore

        # Delete messages for user's projects
        user_projects = db.query(Project).filter(Project.owner_id == owner_id).all()
        prj_ids = [p.id for p in user_projects]
        if prj_ids:
            deleted["messages"] = db.query(Message).filter(Message.project_id.in_(prj_ids)).delete(
                synchronize_session=False)
            deleted["sessions"] = db.query(ChatSession).filter(ChatSession.project_id.in_(prj_ids)).delete(
                synchronize_session=False)
            deleted["projects"] = db.query(Project).filter(Project.id.in_(prj_ids)).delete(synchronize_session=False)

        # Delete billing transactions and account
        deleted["transactions"] = db.query(CreditTransaction).filter(CreditTransaction.owner_id == owner_id).delete(
            synchronize_session=False)
        deleted["account"] = db.query(UserAccount).filter(UserAccount.owner_id == owner_id).delete(
            synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete data: {e}")

    return {"deleted": deleted, "at": datetime.utcnow().isoformat()}
