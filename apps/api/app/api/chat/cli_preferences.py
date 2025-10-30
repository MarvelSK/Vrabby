"""
CLI Preferences API Endpoints
Handles CLI selection and configuration
"""
from typing import Optional, Dict, Any, Tuple
import time

from app.api.deps import get_db
from app.models.projects import Project
from app.services.cli import UnifiedCLIManager
from app.services.cli.base import CLIType
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import hashlib
import json

router = APIRouter()

# Simple in-memory TTL cache for hot endpoints (per-process)
# Keys:
#  - ("available", project_id)
#  - ("status_all", project_id)
#  - ("status_cli", project_id, cli_type)
_TTL_CACHE: Dict[Tuple[str, ...], Tuple[float, Dict[str, Any]]] = {}


def _cache_get(key: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
    v = _TTL_CACHE.get(key)
    if not v:
        return None
    expires_at, payload = v
    if time.time() >= expires_at:
        _TTL_CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: Tuple[str, ...], payload: Dict[str, Any], ttl_seconds: int) -> None:
    _TTL_CACHE[key] = (time.time() + max(1, int(ttl_seconds)), payload)


def _cache_invalidate_project(project_id: str) -> None:
    keys = [k for k in _TTL_CACHE.keys() if len(k) >= 2 and k[1] == project_id]
    for k in keys:
        _TTL_CACHE.pop(k, None)


class CLIPreferenceRequest(BaseModel):
    preferred_cli: str


class ModelPreferenceRequest(BaseModel):
    model_id: str


class CLIStatusResponse(BaseModel):
    cli_type: str
    available: bool
    configured: bool
    error: Optional[str] = None
    models: Optional[list] = None


class AllCLIStatusResponse(BaseModel):
    claude: CLIStatusResponse
    cursor: CLIStatusResponse
    codex: CLIStatusResponse
    qwen: CLIStatusResponse
    gemini: CLIStatusResponse
    preferred_cli: str


@router.get("/{project_id}/cli/available")
async def get_cli_available(project_id: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """Get CLI information for project (used by frontend ProjectSettings) with short TTL cache and ETag"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = ("available", project_id)
    cached = _cache_get(cache_key)
    if cached is None:
        payload = {
            "current_preference": project.preferred_cli,
            "current_model": project.selected_model,
            "fallback_enabled": project.fallback_enabled,
        }
        _cache_set(cache_key, payload, ttl_seconds=60)
    else:
        payload = cached

    # Compute ETag
    etag = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    inm = request.headers.get("if-none-match") or request.headers.get("If-None-Match")
    if inm and inm == etag:
        return Response(status_code=304)

    # Set headers
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"

    return payload


@router.get("/{project_id}/cli-preference")
async def get_cli_preference(project_id: str, db: Session = Depends(get_db)):
    """Get current CLI preference for a project"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Handle projects that might not have these fields set
    preferred_cli = getattr(project, 'preferred_cli', 'claude')
    selected_model = getattr(project, 'selected_model', None)

    return {
        "preferred_cli": preferred_cli,
        "selected_model": selected_model
    }


@router.post("/{project_id}/cli-preference")
async def set_cli_preference(
        project_id: str,
        body: CLIPreferenceRequest,
        db: Session = Depends(get_db)
):
    """Set CLI preference for a project and invalidate caches"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate CLI type
    try:
        cli_type = CLIType(body.preferred_cli)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid CLI type: {body.preferred_cli}"
        )

    # Update project preferences
    project.preferred_cli = cli_type.value
    db.commit()

    # Invalidate cached status for this project
    _cache_invalidate_project(project_id)

    return {
        "preferred_cli": project.preferred_cli,
        "message": f"CLI preference updated to {cli_type.value}"
    }


@router.post("/{project_id}/model-preference")
async def set_model_preference(
        project_id: str,
        body: ModelPreferenceRequest,
        db: Session = Depends(get_db)
):
    """Set model preference for a project and invalidate caches"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.selected_model = body.model_id
    db.commit()

    # Invalidate cached status for this project
    _cache_invalidate_project(project_id)

    return {
        "selected_model": project.selected_model,
        "message": f"Model preference updated to {body.model_id}"
    }


@router.get("/{project_id}/cli-status/{cli_type}", response_model=CLIStatusResponse)
async def get_cli_status(
        project_id: str,
        cli_type: str,
        request: Request,
        response: Response,
        db: Session = Depends(get_db)
):
    """Check status of a specific CLI with short TTL cache and ETag"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        cli_enum = CLIType(cli_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid CLI type: {cli_type}")

    cache_key = ("status_cli", project_id, cli_enum.value)
    cached = _cache_get(cache_key)
    if cached is None:
        cli_manager = UnifiedCLIManager(
            project_id=project.id,
            project_path=project.repo_path,
            session_id="status_check",
            conversation_id="status_check",
            db=db
        )
        status = await cli_manager.check_cli_status(cli_enum)
        payload = {
            "cli_type": cli_type,
            "available": status.get("available", False),
            "configured": status.get("configured", False),
            "error": status.get("error"),
            "models": status.get("models"),
        }
        _cache_set(cache_key, payload, ttl_seconds=30)
    else:
        payload = cached

    etag = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    inm = request.headers.get("if-none-match") or request.headers.get("If-None-Match")
    if inm and inm == etag:
        return Response(status_code=304)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=30"

    return payload


@router.get("/{project_id}/cli-status", response_model=AllCLIStatusResponse)
async def get_all_cli_status(project_id: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """Check status of all CLIs with short TTL cache and ETag"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = ("status_all", project_id)
    cached = _cache_get(cache_key)
    if cached is None:
        preferred_cli = getattr(project, 'preferred_cli', 'claude')
        # Build real status for each CLI using UnifiedCLIManager
        manager = UnifiedCLIManager(
            project_id=project.id,
            project_path=project.repo_path,
            session_id="status_check",
            conversation_id="status_check",
            db=db,
        )
        claude_status = await manager.check_cli_status(CLIType.CLAUDE)
        cursor_status = await manager.check_cli_status(CLIType.CURSOR)
        codex_status = await manager.check_cli_status(CLIType.CODEX)
        qwen_status = await manager.check_cli_status(CLIType.QWEN)
        gemini_status = await manager.check_cli_status(CLIType.GEMINI)
        payload = {
            "claude": {
                "cli_type": "claude",
                "available": claude_status.get("available", False),
                "configured": claude_status.get("configured", False),
                "error": claude_status.get("error"),
                "models": claude_status.get("models"),
            },
            "cursor": {
                "cli_type": "cursor",
                "available": cursor_status.get("available", False),
                "configured": cursor_status.get("configured", False),
                "error": cursor_status.get("error"),
                "models": cursor_status.get("models"),
            },
            "codex": {
                "cli_type": "codex",
                "available": codex_status.get("available", False),
                "configured": codex_status.get("configured", False),
                "error": codex_status.get("error"),
                "models": codex_status.get("models"),
            },
            "qwen": {
                "cli_type": "qwen",
                "available": qwen_status.get("available", False),
                "configured": qwen_status.get("configured", False),
                "error": qwen_status.get("error"),
                "models": qwen_status.get("models"),
            },
            "gemini": {
                "cli_type": "gemini",
                "available": gemini_status.get("available", False),
                "configured": gemini_status.get("configured", False),
                "error": gemini_status.get("error"),
                "models": gemini_status.get("models"),
            },
            "preferred_cli": preferred_cli,
        }
        _cache_set(cache_key, payload, ttl_seconds=30)
    else:
        payload = cached

    etag = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    inm = request.headers.get("if-none-match") or request.headers.get("If-None-Match")
    if inm and inm == etag:
        return Response(status_code=304)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=30"

    # Pydantic model will coerce
    return payload
