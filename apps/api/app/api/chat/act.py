"""
Act Execution API Endpoints
Handles CLI execution and AI actions
"""
import os
import uuid
from datetime import datetime
from typing import List, Optional

from app.api.auth import get_current_user, CurrentUser
from app.api.billing_utils import ensure_user_account, get_balance, adjust_credits
from app.api.deps import get_db
from app.core.config import settings
from app.core.terminal_ui import ui
from app.core.websocket.manager import manager
from app.models.commits import Commit
from app.models.messages import Message
from app.models.projects import Project
from app.models.sessions import Session as ChatSession
from app.models.user_requests import UserRequest
from app.services.cli.base import CLIType
from app.services.cli.unified_manager import UnifiedCLIManager
from app.services.git_ops import commit_all
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import time
import hashlib
import json


def build_project_info(project: Project, db: Session) -> dict:
    """Ensure project has a usable repo path and collect runtime info."""
    repo_path = project.repo_path

    if not repo_path or not os.path.exists(repo_path):
        inferred_path = os.path.join(settings.projects_root, project.id, "repo")
        if os.path.exists(inferred_path):
            project.repo_path = inferred_path
            db.commit()
            repo_path = inferred_path
        else:
            raise HTTPException(
                status_code=409,
                detail="Project repository is not initialized yet. Please wait for project setup to complete."
            )

    return {
        'id': project.id,
        'owner_id': project.owner_id,
        'repo_path': repo_path,
        'preferred_cli': project.preferred_cli or "claude",
        'fallback_enabled': project.fallback_enabled if project.fallback_enabled is not None else True,
        'selected_model': project.selected_model
    }


router = APIRouter()


class ImageAttachment(BaseModel):
    name: str
    # Either base64_data or path must be provided
    base64_data: Optional[str] = None
    path: Optional[str] = None  # Absolute path to image file
    mime_type: str = "image/jpeg"


class ActRequest(BaseModel):
    instruction: str
    conversation_id: str | None = None
    cli_preference: str | None = None
    fallback_enabled: bool = True
    images: List[ImageAttachment] = []
    is_initial_prompt: bool = False
    sub_agent: Optional[str] = None


class ActResponse(BaseModel):
    session_id: str
    conversation_id: str
    status: str
    message: str


def pick_agent(instruction: str) -> Optional[str]:
    try:
        text = (instruction or "").lower()
        if any(w in text for w in ["style", "ui", "component", "tailwind", "css", "tsx", "react"]):
            return "frontend"
        if any(w in text for w in ["sql", "migration", "schema", "alembic", "prisma", "database", "db"]):
            return "db"
        if any(w in text for w in ["test", "jest", "vitest", "playwright", "unit test", "e2e"]):
            return "tests"
        if any(w in text for w in ["api", "backend", "service", "fastapi", "endpoint"]):
            return "backend"
        return None
    except Exception:
        return None


def build_conversation_context(
        project_id: str,
        conversation_id: str | None,
        db: Session,
        *,
        exclude_message_id: str | None = None,
        limit: int = 12
) -> str:
    """Return a formatted snippet of recent chat history for context transfer."""

    query = db.query(Message).filter(Message.project_id == project_id)
    if conversation_id:
        query = query.filter(Message.conversation_id == conversation_id)

    history: list[Message] = []
    for msg in query.order_by(Message.created_at.desc()):
        if exclude_message_id and msg.id == exclude_message_id:
            continue
        if msg.metadata_json and msg.metadata_json.get("hidden_from_ui"):
            continue
        if msg.role not in ("user", "assistant"):
            continue
        history.append(msg)
        if len(history) >= limit:
            break

    if not history:
        return ""

    history.reverse()
    lines = []
    for msg in history:
        role = "User" if msg.role == "user" else "Assistant"
        content = (msg.content or "").strip()
        if not content:
            continue
        lines.append(f"{role}:\n{content}")

    return "\n".join(lines)


async def execute_act_instruction(
        project_id: str,
        instruction: str,
        session_id: str,
        conversation_id: str,
        images: List[ImageAttachment],
        db: Session,
        is_initial_prompt: bool = False
):
    """Execute an ACT instruction - can be called from other modules"""
    try:
        # Get project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get or create session
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            # Use project's preferred CLI
            cli_type = project.preferred_cli or "claude"
            session = ChatSession(
                id=session_id,
                project_id=project_id,
                status="active",
                cli_type=cli_type,
                instruction=instruction,
                started_at=datetime.utcnow()
            )
            db.add(session)
            db.commit()

        # Extract project info to avoid DetachedInstanceError in background task
        project_info = build_project_info(project, db)

        # Execute the task
        return await execute_act_task(
            project_info=project_info,
            session=session,
            instruction=instruction,
            conversation_id=conversation_id,
            images=images,
            db=db,
            cli_preference=None,  # Will use project's preferred CLI
            fallback_enabled=project_info['fallback_enabled'],
            is_initial_prompt=is_initial_prompt
        )
    except Exception as e:
        ui.error(f"Error in execute_act_instruction: {e}", "ACT")
        raise


async def execute_chat_task(
        project_info: dict,
        session: ChatSession,
        instruction: str,
        conversation_id: str,
        images: List[ImageAttachment],
        db: Session,
        cli_preference: CLIType = None,
        fallback_enabled: bool = True,
        is_initial_prompt: bool = False,
        _request_id: str | None = None,
        user_message_id: str | None = None,
        sub_agent: Optional[str] = None,
):
    """Background task for executing Chat instructions"""
    try:
        # Extract project info from dict (to avoid DetachedInstanceError)
        project_id = project_info['id']
        project_repo_path = project_info['repo_path']
        project_preferred_cli = project_info['preferred_cli']
        project_fallback_enabled = project_info['fallback_enabled']
        project_selected_model = project_info['selected_model']

        # Use project's CLI preference if not explicitly provided
        if cli_preference is None:
            try:
                cli_preference = CLIType(project_preferred_cli)
            except ValueError:
                ui.warning(f"Unknown CLI type '{project_preferred_cli}', falling back to Claude", "CHAT")
                cli_preference = CLIType.CLAUDE

        ui.info(f"Using {cli_preference.value} with {project_selected_model or 'default model'}", "CHAT")

        # Update session status to running
        session.status = "running"
        db.commit()

        # Send chat_start event to trigger loading indicator
        await manager.broadcast_to_project(project_id, {
            "type": "chat_start",
            "data": {
                "session_id": session.id,
                "instruction": instruction
            }
        })

        # Initialize CLI manager
        cli_manager = UnifiedCLIManager(
            project_id=project_id,
            project_path=project_repo_path,
            session_id=session.id,
            conversation_id=conversation_id,
            db=db
        )

        # Qwen Coder does not support images yet; drop them to prevent errors
        safe_images = [] if cli_preference == CLIType.QWEN else images

        instruction_payload = instruction
        if not is_initial_prompt:
            context_block = build_conversation_context(
                project_id,
                conversation_id,
                db,
                exclude_message_id=user_message_id
            )
            if context_block:
                instruction_payload = (
                    "You are continuing an ongoing coding session. Reference the recent conversation history below before acting.\n"
                    "<conversation_history>\n"
                    f"{context_block}\n"
                    "</conversation_history>\n\n"
                    "Latest user instruction: \n"
                    f"{instruction}"
                )

        # Lightweight plan-first guard for long instructions (CHAT)
        try:
            _min_chars = int(os.getenv("PLAN_FIRST_MIN_CHARS", "800") or "800")
        except Exception:
            _min_chars = 800
        if len(instruction or "") >= _min_chars:
            plan_prefix = (
                "Before making any changes, write a brief plan (max 6 bullets, under 10 lines) naming exact files to touch and minimal steps. "
                "Then proceed to implement using minimal reads/writes and concise chat output."
            )
            instruction_payload = f"{plan_prefix}\n\n{instruction_payload}"

        # Retry wrapper for robustness (CHAT)
        import os as _os_chat, asyncio as _aio_chat
        _retries = int(_os_chat.getenv('JOB_MAX_RETRIES', '2') or '2')
        _delay = float(_os_chat.getenv('JOB_RETRY_DELAY_SEC', '2') or '2')
        result = None
        last_err = None
        for attempt in range(_retries + 1):
            try:
                _chosen_agent = sub_agent or pick_agent(instruction)
                result = await cli_manager.execute_instruction(
                    instruction=instruction_payload,
                    cli_type=cli_preference,
                    fallback_enabled=project_fallback_enabled,
                    images=safe_images,
                    model=project_selected_model,
                    is_initial_prompt=is_initial_prompt,
                    sub_agent=_chosen_agent
                )
                break
            except Exception as e:
                last_err = e
                ui.warning(f"CHAT attempt {attempt + 1} failed: {e}", "CHAT")
                if attempt < _retries:
                    await _aio_chat.sleep(_delay)
                else:
                    raise

        # Handle result
        if result and result.get("success"):
            # For chat mode, we don't commit changes - just update session status
            session.status = "completed"
            session.completed_at = datetime.utcnow()

        else:
            # Error message
            error_msg = Message(
                id=str(uuid.uuid4()),
                project_id=project_id,
                role="assistant",
                message_type="error",
                content=result.get("error", "Failed to execute chat instruction") if result else "No CLI available",
                metadata_json={
                    "type": "chat_error",
                    "cli_attempted": cli_preference.value
                },
                conversation_id=conversation_id,
                session_id=session.id,
                created_at=datetime.utcnow()
            )
            db.add(error_msg)

            session.status = "failed"
            session.error = result.get("error") if result else "No CLI available"
            session.completed_at = datetime.utcnow()

            # Send error message via WebSocket
            error_data = {
                "id": error_msg.id,
                "role": "assistant",
                "message_type": "error",
                "content": error_msg.content,
                "metadata": error_msg.metadata_json,
                "parent_message_id": None,
                "session_id": session.id,
                "conversation_id": conversation_id
            }
            await manager.broadcast_to_project(project_id, {
                "type": "message",
                "data": error_data,
                "timestamp": error_msg.created_at.isoformat()
            })

        db.commit()

        # Send chat_complete event to clear loading indicator and notify completion
        await manager.broadcast_to_project(project_id, {
            "type": "chat_complete",
            "data": {
                "status": session.status,
                "session_id": session.id
            }
        })

    except Exception as e:
        ui.error(f"Chat execution error: {e}", "CHAT")

        # Save error
        session.status = "failed"
        session.error = str(e)
        session.completed_at = datetime.utcnow()

        # Refund one credit on failure
        try:
            owner_id = project_info.get('owner_id') if isinstance(project_info, dict) else None
            if owner_id:
                adjust_credits(db, owner_id, +1, "refund", "Chat failed")
        except Exception:
            pass

        error_msg = Message(
            id=str(uuid.uuid4()),
            project_id=project_id,
            role="assistant",
            message_type="error",
            content=f"Chat execution failed: {str(e)}",
            metadata_json={"type": "chat_error"},
            conversation_id=conversation_id,
            session_id=session.id,
            created_at=datetime.utcnow()
        )
        db.add(error_msg)
        db.commit()

        # Send chat_complete event even on failure to clear loading indicator
        await manager.broadcast_to_project(project_id, {
            "type": "chat_complete",
            "data": {
                "status": "failed",
                "session_id": session.id,
                "error": str(e)
            }
        })


async def execute_act_task(
        project_info: dict,
        session: ChatSession,
        instruction: str,
        conversation_id: str,
        images: List[ImageAttachment],
        db: Session,
        cli_preference: CLIType = None,
        fallback_enabled: bool = True,
        is_initial_prompt: bool = False,
        request_id: str = None,
        user_message_id: str | None = None,
        sub_agent: Optional[str] = None,
):
    """Background task for executing Act instructions"""
    try:
        # Extract project info from dict (to avoid DetachedInstanceError)
        project_id = project_info['id']
        project_repo_path = project_info['repo_path']
        project_preferred_cli = project_info['preferred_cli']
        project_fallback_enabled = project_info['fallback_enabled']
        project_selected_model = project_info['selected_model']

        # Use project's CLI preference if not explicitly provided
        if cli_preference is None:
            try:
                cli_preference = CLIType(project_preferred_cli)
            except ValueError:
                ui.warning(f"Unknown CLI type '{project_preferred_cli}', falling back to Claude", "ACT")
                cli_preference = CLIType.CLAUDE

        ui.info(f"Using {cli_preference.value} with {project_selected_model or 'default model'}", "ACT")

        # Update session status to running
        session.status = "running"

        # ★ NEW: Update UserRequest status to started
        if request_id:
            user_request = db.query(UserRequest).filter(UserRequest.id == request_id).first()
            if user_request:
                user_request.started_at = datetime.utcnow()
                user_request.cli_type_used = cli_preference.value
                user_request.model_used = project_selected_model

        db.commit()

        # Send act_start event to trigger loading indicator
        await manager.broadcast_to_project(project_id, {
            "type": "act_start",
            "data": {
                "session_id": session.id,
                "instruction": instruction,
                "request_id": request_id
            }
        })

        # Initialize CLI manager
        cli_manager = UnifiedCLIManager(
            project_id=project_id,
            project_path=project_repo_path,
            session_id=session.id,
            conversation_id=conversation_id,
            db=db
        )

        # Qwen Coder does not support images yet; drop them to prevent errors
        safe_images = [] if cli_preference == CLIType.QWEN else images

        instruction_payload = instruction
        if not is_initial_prompt:
            context_block = build_conversation_context(
                project_id,
                conversation_id,
                db,
                exclude_message_id=user_message_id
            )
            if context_block:
                instruction_payload = (
                    "You are continuing an ongoing coding session. Reference the recent conversation history below before acting.\n"
                    "<conversation_history>\n"
                    f"{context_block}\n"
                    "</conversation_history>\n\n"
                    "Latest user instruction: \n"
                    f"{instruction}"
                )

        # Lightweight plan-first guard for long instructions (ACT)
        try:
            _min_chars_act = int(os.getenv("PLAN_FIRST_MIN_CHARS", "800") or "800")
        except Exception:
            _min_chars_act = 800
        if len(instruction or "") >= _min_chars_act:
            plan_prefix_act = (
                "Before making any changes, write a brief plan (max 6 bullets, under 10 lines) naming exact files to touch and minimal steps. "
                "Then proceed to implement using minimal reads/writes and concise chat output."
            )
            instruction_payload = f"{plan_prefix_act}\n\n{instruction_payload}"

        # Retry wrapper for robustness (ACT)
        import os as _os_act, asyncio as _aio_act
        _retries_act = int(_os_act.getenv('JOB_MAX_RETRIES', '2') or '2')
        _delay_act = float(_os_act.getenv('JOB_RETRY_DELAY_SEC', '2') or '2')
        result = None
        for attempt in range(_retries_act + 1):
            try:
                result = await cli_manager.execute_instruction(
                    instruction=instruction_payload,
                    cli_type=cli_preference,
                    fallback_enabled=project_fallback_enabled,
                    images=safe_images,
                    model=project_selected_model,
                    is_initial_prompt=is_initial_prompt,
                    sub_agent=sub_agent
                )
                break
            except Exception as e:
                ui.warning(f"ACT attempt {attempt + 1} failed: {e}", "ACT")
                if attempt < _retries_act:
                    await _aio_act.sleep(_delay_act)
                else:
                    raise

        # Handle result
        ui.info(
            f"Result received: success={result.get('success') if result else None}, cli={result.get('cli_used') if result else None}",
            "ACT")

        if result and result.get("success"):
            # Commit changes if any
            if result.get("has_changes"):
                try:
                    commit_message = f"🤖 {result.get('cli_used', 'AI')}: {instruction[:100]}"
                    commit_result = commit_all(project_repo_path, commit_message)

                    if commit_result["success"]:
                        commit = Commit(
                            id=str(uuid.uuid4()),
                            project_id=project_id,
                            commit_hash=commit_result["commit_hash"],
                            message=commit_message,
                            author="AI Assistant",
                            created_at=datetime.utcnow()
                        )
                        db.add(commit)
                        db.commit()

                        await manager.send_message(project_id, {
                            "type": "commit",
                            "data": {
                                "commit_hash": commit_result["commit_hash"],
                                "message": commit_message,
                                "files_changed": commit_result.get("files_changed", 0)
                            }
                        })
                except Exception as e:
                    ui.warning(f"Commit failed: {e}", "ACT")

            # Update session status only (no success message to user)
            session.status = "completed"
            session.completed_at = datetime.utcnow()

            # ★ NEW: Mark UserRequest as completed successfully
            if request_id:
                user_request = db.query(UserRequest).filter(UserRequest.id == request_id).first()
                if user_request:
                    user_request.is_completed = True
                    user_request.is_successful = True
                    user_request.completed_at = datetime.utcnow()
                    user_request.result_metadata = {
                        "cli_used": result.get("cli_used"),
                        "has_changes": result.get("has_changes", False),
                        "files_modified": result.get("files_modified", []),
                        # provider metrics (may be None)
                        "cost_usd": result.get("cost_usd"),
                        "num_turns": result.get("num_turns"),
                        "duration_ms": result.get("duration_ms"),
                        "api_duration_ms": result.get("api_duration_ms"),
                        "cost_notice_triggered": result.get("cost_notice_triggered", False),
                    }
                    ui.success(f"UserRequest {request_id[:8]}... marked as completed", "ACT")
                else:
                    ui.warning(f"UserRequest {request_id[:8]}... not found for completion", "ACT")

        else:
            # Error message
            error_msg = Message(
                id=str(uuid.uuid4()),
                project_id=project_id,
                role="assistant",
                message_type="error",
                content=result.get("error", "Failed to execute instruction") if result else "No CLI available",
                metadata_json={
                    "type": "act_error",
                    "cli_attempted": cli_preference.value
                },
                conversation_id=conversation_id,
                session_id=session.id,
                created_at=datetime.utcnow()
            )
            db.add(error_msg)

            session.status = "failed"
            session.error = result.get("error") if result else "No CLI available"
            session.completed_at = datetime.utcnow()

            # ★ NEW: Mark UserRequest as completed with failure
            if request_id:
                user_request = db.query(UserRequest).filter(UserRequest.id == request_id).first()
                if user_request:
                    user_request.is_completed = True
                    user_request.is_successful = False
                    user_request.completed_at = datetime.utcnow()
                    user_request.error_message = result.get("error") if result else "No CLI available"
                    ui.warning(f"UserRequest {request_id[:8]}... marked as failed", "ACT")
                else:
                    ui.warning(f"UserRequest {request_id[:8]}... not found for failure marking", "ACT")

            # Send error message via WebSocket
            error_data = {
                "id": error_msg.id,
                "role": "assistant",
                "message_type": "error",
                "content": error_msg.content,
                "metadata": error_msg.metadata_json,
                "parent_message_id": None,
                "session_id": session.id,
                "conversation_id": conversation_id
            }
            await manager.broadcast_to_project(project_id, {
                "type": "message",
                "data": error_data,
                "timestamp": error_msg.created_at.isoformat()
            })

        try:
            db.commit()
            ui.success(f"Database commit successful for request {request_id[:8] if request_id else 'unknown'}...",
                       "ACT")
        except Exception as commit_error:
            ui.error(f"Database commit failed: {commit_error}", "ACT")
            db.rollback()
            raise

        # Send act_complete event to clear loading indicator and notify completion
        await manager.broadcast_to_project(project_id, {
            "type": "act_complete",
            "data": {
                "status": session.status,
                "session_id": session.id,
                "request_id": request_id
            }
        })

    except Exception as e:
        ui.error(f"Execution error: {e}", "ACT")
        import traceback
        ui.error(f"Traceback: {traceback.format_exc()}", "ACT")

        # Save error
        session.status = "failed"
        session.error = str(e)
        session.completed_at = datetime.utcnow()

        # ★ NEW: Mark UserRequest as failed due to exception
        if request_id:
            user_request = db.query(UserRequest).filter(UserRequest.id == request_id).first()
            if user_request:
                user_request.is_completed = True
                user_request.is_successful = False
                user_request.completed_at = datetime.utcnow()
                user_request.error_message = str(e)

        # Refund one credit on failure
        try:
            owner_id = project_info.get('owner_id') if isinstance(project_info, dict) else None
            if owner_id:
                adjust_credits(db, owner_id, +1, "refund", "Act failed")
        except Exception as _:
            pass

        error_msg = Message(
            id=str(uuid.uuid4()),
            project_id=project_id,
            role="assistant",
            message_type="error",
            content=f"Execution failed: {str(e)}",
            metadata_json={"type": "act_error"},
            conversation_id=conversation_id,
            session_id=session.id,
            created_at=datetime.utcnow()
        )
        db.add(error_msg)
        db.commit()

        # Send act_complete event even on failure to clear loading indicator
        await manager.broadcast_to_project(project_id, {
            "type": "act_complete",
            "data": {
                "status": "failed",
                "session_id": session.id,
                "request_id": request_id,
                "error": str(e)
            }
        })


@router.post("/{project_id}/act", response_model=ActResponse)
async def run_act(
        project_id: str,
        body: ActRequest,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: CurrentUser = Depends(get_current_user)
):
    """Execute instruction using unified CLI system"""
    ui.info(f"Starting execution: {body.instruction[:50]}...", "ACT")
    ui.info(f"Initial prompt flag: {body.is_initial_prompt}", "ACT")

    project = db.get(Project, project_id)
    if not project or project.owner_id != current_user["id"]:
        ui.error(f"Project {project_id} not found or access denied", "ACT API")
        raise HTTPException(status_code=404, detail="Project not found")

    # Readiness guard: block prompts until CLI/agent initialized
    try:
        cli_preference_check = CLIType(body.cli_preference or project.preferred_cli)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid CLI type: {body.cli_preference}")
    try:
        cli_manager_chk = UnifiedCLIManager(
            project_id=project_id,
            project_path=project.repo_path or "",
            session_id="status_check",
            conversation_id="status_check",
            db=db,
        )
        status_chk = await cli_manager_chk.check_cli_status(cli_preference_check, project.selected_model)
        if not (status_chk.get("available") and status_chk.get("configured")):
            raise HTTPException(
                status_code=425,
                detail="Selected CLI/agent is not initialized yet. Please wait a moment and try again.",
                headers={"Retry-After": "10"},
            )
    except HTTPException:
        raise
    except Exception as e:
        ui.warning(f"CLI status check failed: {e}", "ACT API")
        raise HTTPException(
            status_code=425,
            detail="CLI/agent is not ready yet. Please wait a moment and try again.",
            headers={"Retry-After": "10"},
        )

    # Credits enforcement: token-based debit (approximate by instruction length)
    try:
        ensure_user_account(db, current_user["id"])  # ensure exists
        approx_tokens = max(1, int(len(body.instruction or "") / 4))
        tokens_per_credit = max(1, settings.tokens_per_credit)
        # Ceiling division for debit units
        debit = max(1, (approx_tokens + tokens_per_credit - 1) // tokens_per_credit)
        if get_balance(db, current_user["id"]) < debit:
            raise HTTPException(status_code=402, detail="Out of credits. Please subscribe or purchase credits.")
        adjust_credits(
            db,
            current_user["id"],
            -debit,
            "spend",
            f"Act request; approx_tokens={approx_tokens}; rate=1 credit/{tokens_per_credit} tokens",
        )
    except HTTPException:
        raise
    except Exception as e:
        ui.error(f"Credit spend failed: {e}", "ACT API")
        raise HTTPException(status_code=402, detail="Unable to spend credits")

    # Determine CLI preference
    cli_preference = CLIType(body.cli_preference or project.preferred_cli)
    fallback_enabled = body.fallback_enabled if body.fallback_enabled is not None else project.fallback_enabled
    conversation_id = body.conversation_id or str(uuid.uuid4())

    # 🔍 DEBUG: Log incoming request data
    print(f"📥 ACT Request - Project: {project_id}")
    print(f"📥 Instruction: {body.instruction[:100]}...")
    print(f"📥 Images count: {len(body.images)}")
    print(f"📥 Images data: {body.images}")
    for i, img in enumerate(body.images):
        print(f"📥 Image {i + 1}: {img}")
        if hasattr(img, '__dict__'):
            print(f"📥 Image {i + 1} dict: {img.__dict__}")

    # Extract image paths and build attachments for metadata/WS
    image_paths = []
    attachments = []
    import os as _os

    print(f"🔍 Processing {len(body.images)} images...")
    for i, img in enumerate(body.images):
        print(f"🔍 Processing image {i + 1}: {img}")

        img_dict = img if isinstance(img, dict) else img.__dict__ if hasattr(img, '__dict__') else {}
        print(f"🔍 Image {i + 1} converted to dict: {img_dict}")

        p = img_dict.get('path')
        n = img_dict.get('name')
        print(f"🔍 Image {i + 1} - path: {p}, name: {n}")

        if p:
            print(f"🔍 Adding path to image_paths: {p}")
            image_paths.append(p)
            try:
                fname = _os.path.basename(p)
                print(f"🔍 Processing path: {p}")
                print(f"🔍 Extracted filename: {fname}")
                if fname and fname.strip():
                    attachment = {
                        "name": n or fname,
                        "url": f"/api/assets/{project_id}/{fname}"
                    }
                    print(f"🔍 Created attachment: {attachment}")
                    attachments.append(attachment)
                else:
                    print(f"❌ Failed to extract filename from: {p}")
            except Exception as e:
                print(f"❌ Exception processing path {p}: {e}")
                pass
        elif n:
            print(f"🔍 Adding name to image_paths: {n}")
            image_paths.append(n)
        else:
            print(f"❌ Image {i + 1} has neither path nor name!")

    print(f"🔍 Final image_paths: {image_paths}")
    print(f"🔍 Final attachments: {attachments}")

    # Save user instruction as message (with image paths in content for display)
    message_content = body.instruction
    if image_paths:
        image_refs = [f"Image #{i + 1} path: {path}" for i, path in enumerate(image_paths)]
        message_content = f"{body.instruction}\n\n{chr(10).join(image_refs)}"

    user_message = Message(
        id=str(uuid.uuid4()),
        project_id=project_id,
        role="user",
        message_type="chat",
        content=message_content,
        metadata_json={
            "type": "act_instruction",
            "cli_preference": cli_preference.value,
            "fallback_enabled": fallback_enabled,
            "has_images": len(body.images) > 0,
            "image_paths": image_paths,
            "attachments": attachments
        },
        conversation_id=conversation_id,
        created_at=datetime.utcnow()
    )
    db.add(user_message)

    # Create session
    session = ChatSession(
        id=str(uuid.uuid4()),
        project_id=project_id,
        status="active",
        instruction=body.instruction,
        cli_type=cli_preference.value,
        started_at=datetime.utcnow()
    )
    db.add(session)

    # ★ NEW: Create UserRequest for tracking
    request_id = str(uuid.uuid4())
    user_request = UserRequest(
        id=request_id,
        project_id=project_id,
        user_message_id=user_message.id,
        session_id=session.id,
        instruction=body.instruction,
        request_type="act",
        created_at=datetime.utcnow()
    )
    db.add(user_request)

    try:
        db.commit()
    except Exception as e:
        ui.error(f"Database commit failed: {e}", "ACT API")
        raise

    # Send initial messages
    try:
        await manager.send_message(project_id, {
            "type": "message",
            "data": {
                "id": user_message.id,
                "role": "user",
                "message_type": "chat",
                "content": message_content,
                "metadata_json": {**(user_message.metadata_json or {}), "sub_agent": body.sub_agent or pick_agent(body.instruction)},
                "parent_message_id": None,
                "session_id": session.id,
                "conversation_id": conversation_id,
                "request_id": request_id,
                "created_at": user_message.created_at.isoformat()
            },
            "timestamp": user_message.created_at.isoformat()
        })
    except Exception as e:
        ui.error(f"WebSocket failed: {e}", "ACT API")

    # Extract project info to avoid DetachedInstanceError in background task
    project_info = build_project_info(project, db)

    # Add background task
    chosen_agent = body.sub_agent or pick_agent(body.instruction)
    background_tasks.add_task(
        execute_act_task,
        project_info,
        session,
        body.instruction,
        conversation_id,
        body.images,
        db,
        cli_preference,
        fallback_enabled,
        body.is_initial_prompt,
        request_id,
        user_message.id,
        chosen_agent
    )
    return ActResponse(
        session_id=session.id,
        conversation_id=conversation_id,
        status="running",
        message="Act execution started"
    )


@router.post("/{project_id}/chat", response_model=ActResponse)
async def run_chat(
        project_id: str,
        body: ActRequest,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: CurrentUser = Depends(get_current_user)
):
    """Execute chat instruction using unified CLI system (same as act but different event type)"""
    ui.info(f"Starting chat: {body.instruction[:50]}...", "CHAT")

    project = db.get(Project, project_id)
    if not project or project.owner_id != current_user["id"]:
        ui.error(f"Project {project_id} not found or access denied", "CHAT API")
        raise HTTPException(status_code=404, detail="Project not found")

    # Readiness guard: block prompts until CLI/agent initialized
    try:
        cli_preference_check = CLIType(body.cli_preference or project.preferred_cli)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid CLI type: {body.cli_preference}")
    try:
        cli_manager_chk = UnifiedCLIManager(
            project_id=project_id,
            project_path=project.repo_path or "",
            session_id="status_check",
            conversation_id="status_check",
            db=db,
        )
        status_chk = await cli_manager_chk.check_cli_status(cli_preference_check, project.selected_model)
        if not (status_chk.get("available") and status_chk.get("configured")):
            raise HTTPException(
                status_code=425,
                detail="Selected CLI/agent is not initialized yet. Please wait a moment and try again.",
                headers={"Retry-After": "10"},
            )
    except HTTPException:
        raise
    except Exception as e:
        ui.warning(f"CLI status check failed: {e}", "CHAT API")
        raise HTTPException(
            status_code=425,
            detail="CLI/agent is not ready yet. Please wait a moment and try again.",
            headers={"Retry-After": "10"},
        )

    # Credits enforcement: token-based debit (approximate by instruction length)
    try:
        ensure_user_account(db, current_user["id"])  # ensure exists
        approx_tokens = max(1, int(len(body.instruction or "") / 4))
        tokens_per_credit = max(1, settings.tokens_per_credit)
        debit = max(1, (approx_tokens + tokens_per_credit - 1) // tokens_per_credit)
        if get_balance(db, current_user["id"]) < debit:
            raise HTTPException(status_code=402, detail="Out of credits. Please subscribe or purchase credits.")
        adjust_credits(
            db,
            current_user["id"],
            -debit,
            "spend",
            f"Chat request; approx_tokens={approx_tokens}; rate=1 credit/{tokens_per_credit} tokens",
        )
    except HTTPException:
        raise
    except Exception as e:
        ui.error(f"Credit spend failed: {e}", "CHAT API")
        raise HTTPException(status_code=402, detail="Unable to spend credits")

    # Determine CLI preference
    cli_preference = CLIType(body.cli_preference or project.preferred_cli)
    fallback_enabled = body.fallback_enabled if body.fallback_enabled is not None else project.fallback_enabled
    conversation_id = body.conversation_id or str(uuid.uuid4())

    # Extract image paths and build attachments for metadata/WS
    image_paths = []
    attachments = []
    import os as _os2
    for img in body.images:
        img_dict = img if isinstance(img, dict) else img.__dict__ if hasattr(img, '__dict__') else {}
        p = img_dict.get('path')
        n = img_dict.get('name')
        if p:
            image_paths.append(p)
            try:
                fname = _os2.path.basename(p)
                print(f"🔍 [CHAT] Processing path: {p}")
                print(f"🔍 [CHAT] Extracted filename: {fname}")
                if fname and fname.strip():
                    attachment = {
                        "name": n or fname,
                        "url": f"/api/assets/{project_id}/{fname}"
                    }
                    print(f"🔍 [CHAT] Created attachment: {attachment}")
                    attachments.append(attachment)
                else:
                    print(f"❌ [CHAT] Failed to extract filename from: {p}")
            except Exception as e:
                print(f"❌ [CHAT] Exception processing path {p}: {e}")
                pass
        elif n:
            image_paths.append(n)

    # Save user instruction as message (with image paths in content for display)
    message_content = body.instruction
    if image_paths:
        image_refs = [f"Image #{i + 1} path: {path}" for i, path in enumerate(image_paths)]
        message_content = f"{body.instruction}\n\n{chr(10).join(image_refs)}"

    user_message = Message(
        id=str(uuid.uuid4()),
        project_id=project_id,
        role="user",
        message_type="chat",
        content=message_content,
        metadata_json={
            "type": "chat_instruction",
            "cli_preference": cli_preference.value,
            "fallback_enabled": fallback_enabled,
            "has_images": len(body.images) > 0,
            "image_paths": image_paths,
            "attachments": attachments
        },
        conversation_id=conversation_id,
        created_at=datetime.utcnow()
    )
    db.add(user_message)

    # Create session
    session = ChatSession(
        id=str(uuid.uuid4()),
        project_id=project_id,
        status="active",
        instruction=body.instruction,
        cli_type=cli_preference.value,
        started_at=datetime.utcnow()
    )
    db.add(session)

    try:
        db.commit()
    except Exception as e:
        ui.error(f"Database commit failed: {e}", "CHAT API")
        raise

    # Send initial messages
    try:
        await manager.send_message(project_id, {
            "type": "message",
            "data": {
                "id": user_message.id,
                "role": "user",
                "message_type": "chat",
                "content": message_content,
                "metadata_json": {**(user_message.metadata_json or {}), "sub_agent": body.sub_agent or pick_agent(body.instruction)},
                "parent_message_id": None,
                "session_id": session.id,
                "conversation_id": conversation_id,
                "created_at": user_message.created_at.isoformat()
            },
            "timestamp": user_message.created_at.isoformat()
        })
    except Exception as e:
        ui.error(f"WebSocket failed: {e}", "CHAT API")

    # Extract project info (with validated repo_path) to avoid DetachedInstanceError
    project_info = build_project_info(project, db)

    # Add background task for chat (same as act but with different event type)
    chosen_agent = body.sub_agent or pick_agent(body.instruction)
    background_tasks.add_task(
        execute_chat_task,
        project_info,
        session,
        body.instruction,
        conversation_id,
        body.images,
        db,
        cli_preference,
        fallback_enabled,
        body.is_initial_prompt,
        None,
        user_message.id,
        chosen_agent
    )

    return ActResponse(
        session_id=session.id,
        conversation_id=conversation_id,
        status="running",
        message="Chat execution started"
    )


# --- Metrics aggregation endpoint (token/cost visibility) ---
_METRICS_CACHE: dict[tuple[str, int], tuple[float, dict]] = {}

@router.get("/{project_id}/metrics")
async def get_project_metrics(
    project_id: str,
    limit: int = 30,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
):
    """Return recent execution metrics for a project with rolling medians and outlier flags.

    Adds a tiny in-memory cache (10s) and ETag support to avoid recompute storms.
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    limit = max(1, min(int(limit or 30), 200))

    # Short TTL cache
    try:
        cache_key = (project_id, limit)
        now = time.time()
        cached = _METRICS_CACHE.get(cache_key)
        if cached and cached[0] > now:
            payload = cached[1]
            etag = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            inm = request.headers.get("if-none-match") if request else None
            if inm and inm == etag:
                return Response(status_code=304)
            if response is not None:
                response.headers["ETag"] = etag
                response.headers["Cache-Control"] = "private, max-age=10"
            return payload
    except Exception:
        pass

    rows: list[UserRequest] = (
        db.query(UserRequest)
        .filter(UserRequest.project_id == project_id)
        .order_by(UserRequest.created_at.desc())
        .limit(limit)
        .all()
    )

    def _num(x):
        try:
            return float(x)
        except Exception:
            return None

    costs: list[float] = []
    turns: list[int] = []
    for r in rows:
        meta = r.result_metadata or {}
        c = _num(meta.get("cost_usd")) if isinstance(meta, dict) else None
        t = meta.get("num_turns") if isinstance(meta, dict) else None
        if c is not None:
            costs.append(c)
        try:
            if t is not None:
                turns.append(int(t))
        except Exception:
            pass

    def _median(vals: list[float]) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        n = len(s)
        mid = n // 2
        if n % 2 == 1:
            return float(s[mid])
        return float((s[mid - 1] + s[mid]) / 2.0)

    median_cost = _median(costs)
    median_turns = _median(turns)

    OUTLIER_MULT = float(os.getenv("METRICS_OUTLIER_MULT", "2.5") or "2.5")

    items = []
    for r in rows:
        meta = r.result_metadata or {}
        cost = _num(meta.get("cost_usd")) if isinstance(meta, dict) else None
        t = meta.get("num_turns") if isinstance(meta, dict) else None
        item = {
            "id": r.id,
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            "request_type": r.request_type,
            "is_completed": r.is_completed,
            "is_successful": r.is_successful,
            "cost_usd": cost,
            "num_turns": int(t) if isinstance(t, (int, float)) else None,
            "duration_ms": meta.get("duration_ms") if isinstance(meta, dict) else None,
            "api_duration_ms": meta.get("api_duration_ms") if isinstance(meta, dict) else None,
            "cost_notice_triggered": bool(meta.get("cost_notice_triggered")) if isinstance(meta, dict) else False,
        }
        item["outlier"] = {
            "cost": (cost is not None and median_cost > 0 and cost >= median_cost * OUTLIER_MULT),
            "turns": (item["num_turns"] is not None and median_turns > 0 and item["num_turns"] >= median_turns * OUTLIER_MULT),
        }
        items.append(item)

    payload = {
        "project_id": project_id,
        "limit": limit,
        "count": len(items),
        "medians": {"cost_usd": median_cost, "num_turns": median_turns},
        "outlier_multiplier": OUTLIER_MULT,
        "items": items,
    }

    # Store cache and set headers
    try:
        _METRICS_CACHE[cache_key] = (time.time() + 10, payload)
        if response is not None:
            etag = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = "private, max-age=10"
    except Exception:
        pass

    return payload
