"""Unified CLI Manager implementation.

Moved from unified_manager.py to a dedicated module.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import os
from datetime import datetime

from app.core.terminal_ui import ui
from app.core.websocket.manager import manager as ws_manager
from app.models.messages import Message

from .adapters import ClaudeCodeCLI, CursorAgentCLI, CodexCLI, QwenCLI, GeminiCLI
from .base import CLIType


class UnifiedCLIManager:
    """Unified manager for all CLI implementations"""

    def __init__(
            self,
            project_id: str,
            project_path: str,
            session_id: str,
            conversation_id: str,
            db: Any,  # SQLAlchemy Session
    ):
        self.project_id = project_id
        self.project_path = project_path
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.db = db

        # Initialize CLI adapters with database session
        self.cli_adapters = {
            CLIType.CLAUDE: ClaudeCodeCLI(),  # Use SDK implementation if available
            CLIType.CURSOR: CursorAgentCLI(db_session=db),
            CLIType.CODEX: CodexCLI(db_session=db),
            CLIType.QWEN: QwenCLI(db_session=db),
            CLIType.GEMINI: GeminiCLI(db_session=db),
        }

    async def _attempt_fallback(
            self,
            failed_cli: CLIType,
            instruction: str,
            images: Optional[List[Dict[str, Any]]],
            model: Optional[str],
            is_initial_prompt: bool,
    ) -> Optional[Dict[str, Any]]:
        fallback_type = CLIType.CLAUDE
        if failed_cli == fallback_type:
            return None

        fallback_cli = self.cli_adapters.get(fallback_type)
        if not fallback_cli:
            ui.warning("Fallback CLI Claude not configured", "CLI")
            return None

        status = await fallback_cli.check_availability()
        if not status.get("available") or not status.get("configured"):
            ui.error(
                f"Fallback CLI {fallback_type.value} unavailable: {status.get('error', 'unknown error')}",
                "CLI",
            )
            return None

        ui.warning(
            f"CLI {failed_cli.value} unavailable; falling back to {fallback_type.value}",
            "CLI",
        )

        try:
            result = await self._execute_with_cli(
                fallback_cli, instruction, images, model, is_initial_prompt, sub_agent=None
            )
            result["fallback_used"] = True
            result["fallback_from"] = failed_cli.value
            return result
        except Exception as error:
            ui.error(
                f"Fallback CLI {fallback_type.value} failed: {error}",
                "CLI",
            )
            return None

    async def execute_instruction(
            self,
            instruction: str,
            cli_type: CLIType,
            fallback_enabled: bool = True,  # Kept for backward compatibility but not used
            images: Optional[List[Dict[str, Any]]] = None,
            model: Optional[str] = None,
            is_initial_prompt: bool = False,
            sub_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute instruction with specified CLI"""

        # Try the specified CLI
        if cli_type in self.cli_adapters:
            cli = self.cli_adapters[cli_type]

            # Check if CLI is available
            status = await cli.check_availability()
            if status.get("available") and status.get("configured"):
                try:
                    return await self._execute_with_cli(
                        cli, instruction, images, model, is_initial_prompt, sub_agent=sub_agent
                    )
                except Exception as e:
                    ui.error(f"CLI {cli_type.value} failed: {e}", "CLI")
                    if fallback_enabled:
                        fallback_result = await self._attempt_fallback(
                            cli_type, instruction, images, model, is_initial_prompt
                        )
                        if fallback_result:
                            return fallback_result
                    return {
                        "success": False,
                        "error": str(e),
                        "cli_attempted": cli_type.value,
                    }
            else:
                ui.warning(
                    f"CLI {cli_type.value} unavailable: {status.get('error', 'CLI not available')}",
                    "CLI",
                )
                if fallback_enabled:
                    fallback_result = await self._attempt_fallback(
                        cli_type, instruction, images, model, is_initial_prompt
                    )
                    if fallback_result:
                        return fallback_result
                return {
                    "success": False,
                    "error": status.get("error", "CLI not available"),
                    "cli_attempted": cli_type.value,
                }

        if fallback_enabled:
            fallback_result = await self._attempt_fallback(
                cli_type, instruction, images, model, is_initial_prompt
            )
            if fallback_result:
                return fallback_result

        return {
            "success": False,
            "error": f"CLI type {cli_type.value} not implemented",
            "cli_attempted": cli_type.value,
        }

    async def _execute_with_cli(
            self,
            cli,
            instruction: str,
            images: Optional[List[Dict[str, Any]]],
            model: Optional[str] = None,
            is_initial_prompt: bool = False,
            sub_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute instruction with a specific CLI"""

        ui.info(f"Starting {cli.cli_type.value} execution", "CLI")
        if model:
            ui.debug(f"Using model: {model}", "CLI")

        messages_collected: List[Message] = []
        has_changes = False
        files_modified: set[str] = set()
        has_error = False  # Track if any error occurred
        result_success: Optional[bool] = None  # Track result event success status
        # Metrics from provider result (if available)
        cost_usd: Optional[float] = None
        num_turns: Optional[int] = None
        duration_ms: Optional[int] = None
        api_duration_ms: Optional[int] = None

        # Log callback
        async def log_callback(message: str):
            # CLI output logs are now only printed to console, not sent to UI
            pass

        async for message in cli.execute_with_streaming(
                instruction=instruction,
                project_path=self.project_path,
                session_id=self.session_id,
                log_callback=log_callback,
                images=images,
                model=model,
                is_initial_prompt=is_initial_prompt,
                sub_agent=sub_agent,
        ):
            # Check for error messages or result status
            if message.message_type == "error":
                has_error = True
                ui.error(f"CLI error detected: {message.content[:100]}", "CLI")

            if message.metadata_json:
                files = message.metadata_json.get("files_modified")
                if isinstance(files, (list, tuple, set)):
                    files_modified.update(str(f) for f in files)

            # Capture provider result metrics when available (adapter emits a hidden 'result' message)
            if message.message_type == "result" and message.metadata_json:
                try:
                    if "total_cost_usd" in message.metadata_json:
                        cost_usd = float(message.metadata_json.get("total_cost_usd") or 0)
                    if "num_turns" in message.metadata_json:
                        num_turns = int(message.metadata_json.get("num_turns") or 0)
                    if "duration_ms" in message.metadata_json:
                        duration_ms = int(message.metadata_json.get("duration_ms") or 0)
                    if "duration_api_ms" in message.metadata_json:
                        api_duration_ms = int(message.metadata_json.get("duration_api_ms") or 0)
                except Exception:
                    pass

            # Check for Cursor result event (stored in metadata)
            if message.metadata_json:
                event_type = message.metadata_json.get("event_type")
                original_event = message.metadata_json.get("original_event", {})

                if event_type == "result" or original_event.get("type") == "result":
                    # Cursor sends result event with success/error status
                    is_error = original_event.get("is_error", False)
                    subtype = original_event.get("subtype", "")

                    # DEBUG: Log the complete result event structure
                    ui.info(f"🔍 [Cursor] Result event received:", "DEBUG")
                    ui.info(f"   Full event: {original_event}", "DEBUG")
                    ui.info(f"   is_error: {is_error}", "DEBUG")
                    ui.info(f"   subtype: '{subtype}'", "DEBUG")
                    ui.info(f"   has event.result: {'result' in original_event}", "DEBUG")
                    ui.info(f"   has event.status: {'status' in original_event}", "DEBUG")
                    ui.info(f"   has event.success: {'success' in original_event}", "DEBUG")

                    if is_error or subtype == "error":
                        has_error = True
                        result_success = False
                        ui.error(
                            f"Cursor result: error (is_error={is_error}, subtype='{subtype}')",
                            "CLI",
                        )
                    elif subtype == "success":
                        result_success = True
                        ui.success(
                            f"Cursor result: success (subtype='{subtype}')", "CLI"
                        )
                    else:
                        # Handle case where subtype is not "success" but execution was successful
                        ui.warning(
                            f"Cursor result: no explicit success subtype (subtype='{subtype}', is_error={is_error})",
                            "CLI",
                        )
                        # If there's no error indication, assume success
                        if not is_error:
                            result_success = True
                            ui.success(
                                f"Cursor result: assuming success (no error detected)", "CLI"
                            )

            # Save message to database
            message.project_id = self.project_id
            message.conversation_id = self.conversation_id
            self.db.add(message)
            self.db.commit()

            messages_collected.append(message)

            # Check if message should be hidden from UI
            should_hide = (
                    message.metadata_json and message.metadata_json.get("hidden_from_ui", False)
            )

            # Send message via WebSocket only if not hidden
            if not should_hide:
                ws_message = {
                    "type": "message",
                    "data": {
                        "id": message.id,
                        "role": message.role,
                        "message_type": message.message_type,
                        "content": message.content,
                        "metadata": message.metadata_json,
                        "parent_message_id": getattr(message, "parent_message_id", None),
                        "session_id": message.session_id,
                        "conversation_id": self.conversation_id,
                        "created_at": message.created_at.isoformat(),
                    },
                    "timestamp": message.created_at.isoformat(),
                }
                try:
                    await ws_manager.send_message(self.project_id, ws_message)
                except Exception as e:
                    ui.error(f"WebSocket send failed: {e}", "Message")

            # Check if changes were made
            if message.metadata_json and "changes_made" in message.metadata_json:
                has_changes = True

        # Determine final success status
        # For Cursor: check result_success if available, otherwise check has_error
        # For others: check has_error
        ui.info(
            f"🔍 Final success determination: cli_type={cli.cli_type}, result_success={result_success}, has_error={has_error}",
            "CLI",
        )

        if cli.cli_type == CLIType.CURSOR and result_success is not None:
            success = result_success
            ui.info(f"Using Cursor result_success: {result_success}", "CLI")
        else:
            success = not has_error
            ui.info(f"Using has_error logic: not {has_error} = {success}", "CLI")

        if success:
            ui.success(
                f"Streaming completed successfully. Total messages: {len(messages_collected)}",
                "CLI",
            )
        else:
            ui.error(
                f"Streaming completed with errors. Total messages: {len(messages_collected)}",
                "CLI",
            )

        # Soft guardrail: if cost/turns exceed thresholds, emit a short notice message
        cost_threshold = 0.0
        turns_threshold = 0
        try:
            cost_threshold = float(os.getenv("COST_NOTICE_USD", "0.75") or "0.75")
        except Exception:
            cost_threshold = 0.75
        try:
            turns_threshold = int(os.getenv("TURNS_NOTICE_MIN", "10") or "10")
        except Exception:
            turns_threshold = 10

        notice_triggered = False
        if ((cost_usd is not None and cost_usd >= cost_threshold) or (num_turns is not None and num_turns >= turns_threshold)):
            try:
                notice_triggered = True
                from uuid import uuid4
                notice = Message(
                    id=str(uuid4()),
                    project_id=self.project_id,
                    role="assistant",
                    message_type="chat",
                    content=(
                        f"Notice: last turn used ~${cost_usd:.2f} and {num_turns or 0} tool turns. "
                        "Next: propose a brief plan first and keep reads small; avoid large listings."
                    ),
                    metadata_json={
                        "type": "cost_notice",
                        "cost_usd": cost_usd,
                        "num_turns": num_turns,
                        "duration_ms": duration_ms,
                        "api_duration_ms": api_duration_ms,
                        "thresholds": {"cost_usd": cost_threshold, "num_turns": turns_threshold},
                    },
                    session_id=self.session_id,
                    conversation_id=self.conversation_id,
                    created_at=datetime.utcnow(),
                )
                self.db.add(notice)
                self.db.commit()
                try:
                    await ws_manager.send_message(self.project_id, {
                        "type": "message",
                        "data": {
                            "id": notice.id,
                            "role": notice.role,
                            "message_type": notice.message_type,
                            "content": notice.content,
                            "metadata": notice.metadata_json,
                            "parent_message_id": None,
                            "session_id": notice.session_id,
                            "conversation_id": notice.conversation_id,
                            "created_at": notice.created_at.isoformat(),
                        },
                        "timestamp": notice.created_at.isoformat(),
                    })
                except Exception as e:
                    ui.error(f"WebSocket send failed (notice): {e}", "Message")
            except Exception as e:
                ui.warning(f"Failed to emit cost/turns notice: {e}", "CLI")

        # Append concise session summary to context/session-summary.md
        try:
            import os as _os_sum
            ctx_dir = _os_sum.path.join(self.project_path, "context")
            _os_sum.makedirs(ctx_dir, exist_ok=True)
            sum_path = _os_sum.path.join(ctx_dir, "session-summary.md")
            ts = datetime.utcnow().isoformat()
            files_list = list(files_modified) if files_modified else []
            files_preview = ", ".join(sorted(files_list)[:8])
            if files_list and len(files_list) > 8:
                files_preview += f" +{len(files_list)-8}"
            cost_str = f"{(cost_usd or 0):.2f}"
            line = (
                f"{ts} | cli={cli.cli_type.value} | sub_agent={sub_agent or '-'} | "
                f"success={success} | changes={bool(files_list)} | files=[{files_preview}] | "
                f"cost=${cost_str} | turns={num_turns or 0}\n"
            )
            # Initialize header if not exists
            if not _os_sum.path.exists(sum_path):
                with open(sum_path, "w", encoding="utf-8") as f:
                    f.write("# Session Summary\n\n")
            # Append line
            with open(sum_path, "a", encoding="utf-8") as f:
                f.write(line)
            # Trim to last 200 lines (preserve header if present)
            try:
                with open(sum_path, "r", encoding="utf-8") as f:
                    _lines = f.readlines()
                _header = []
                _body = _lines
                if _lines and _lines[0].startswith("#"):
                    # keep first two lines (# header and blank)
                    _header = _lines[:2]
                    _body = _lines[2:]
                if len(_body) > 200:
                    _body = _body[-200:]
                with open(sum_path, "w", encoding="utf-8") as f:
                    f.writelines(_header + _body)
            except Exception:
                pass
        except Exception as e:
            ui.warning(f"Failed to update session-summary.md: {e}", "CLI")

        return {
            "success": success,
            "cli_used": cli.cli_type.value,
            "has_changes": has_changes,
            "message": f"{'Successfully' if success else 'Failed to'} execute with {cli.cli_type.value}",
            "error": "Execution failed" if not success else None,
            "messages_count": len(messages_collected),
            # metrics
            "cost_usd": cost_usd,
            "num_turns": num_turns,
            "duration_ms": duration_ms,
            "api_duration_ms": api_duration_ms,
            "cost_notice_triggered": notice_triggered,
            "files_modified": list(files_modified) if files_modified else [],
        }

        # End _execute_with_cli

    async def check_cli_status(
            self, cli_type: CLIType, selected_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check status of a specific CLI"""
        if cli_type in self.cli_adapters:
            status = await self.cli_adapters[cli_type].check_availability()

            # Add model validation if model is specified
            if selected_model and status.get("available"):
                cli = self.cli_adapters[cli_type]
                if not cli.is_model_supported(selected_model):
                    status[
                        "model_warning"
                    ] = f"Model '{selected_model}' may not be supported by {cli_type.value}"
                    status["suggested_models"] = status.get("default_models", [])
                else:
                    status["selected_model"] = selected_model
                    status["model_valid"] = True

            return status
        return {
            "available": False,
            "configured": False,
            "error": f"CLI type {cli_type.value} not implemented",
        }


__all__ = ["UnifiedCLIManager"]
