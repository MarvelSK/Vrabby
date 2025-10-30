"""Claude Code provider implementation.

Moved from unified_manager.py to a dedicated adapter module.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from app.core.terminal_ui import ui
from app.models.messages import Message
from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions

from ..base import BaseCLI, CLIType


class ClaudeCodeCLI(BaseCLI):
    """Claude Code Python SDK implementation"""

    def __init__(self):
        super().__init__(CLIType.CLAUDE)
        self.session_mapping: Dict[str, str] = {}
        # Cache last-known session metadata to avoid unnecessary re-initialization
        # Keyed by project_id: { 'model': str, 'updated_at': datetime.isoformat }
        self._last_session_meta: Dict[str, Dict[str, Any]] = {}

    async def check_availability(self) -> Dict[str, Any]:
        """Check if Claude Code CLI is available"""
        try:
            # First try to check if claude CLI is installed and working
            result = await asyncio.create_subprocess_shell(
                "claude -h",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                return {
                    "available": False,
                    "configured": False,
                    "error": (
                        "Claude Code CLI not installed or not working.\n\nTo install:\n"
                        "1. Install Claude Code: pnpm add -g @anthropic-ai/claude-code\n"
                        "2. Login to Claude: claude login\n3. Try running your prompt again"
                    ),
                }

            # Check if help output contains expected content
            help_output = stdout.decode() + stderr.decode()
            if "claude" not in help_output.lower():
                return {
                    "available": False,
                    "configured": False,
                    "error": (
                        "Claude Code CLI not responding correctly.\n\nPlease try:\n"
                        "1. Reinstall: pnpm add -g @anthropic-ai/claude-code\n"
                        "2. Login: claude login\n3. Check installation: claude -h"
                    ),
                }

            return {
                "available": True,
                "configured": True,
                "mode": "CLI",
                "models": self.get_supported_models(),
                "default_models": [
                    "claude-sonnet-4-5-20250929",
                    "claude-opus-4-1-20250805",
                ],
            }
        except Exception as e:
            return {
                "available": False,
                "configured": False,
                "error": (
                    f"Failed to check Claude Code CLI: {str(e)}\n\nTo install:\n"
                    "1. Install Claude Code: pnpm add -g @anthropic-ai/claude-code\n"
                    "2. Login to Claude: claude login"
                ),
            }

    async def execute_with_streaming(
            self,
            instruction: str,
            project_path: str,
            session_id: Optional[str] = None,
            log_callback: Optional[Callable[[str], Any]] = None,
            images: Optional[List[Dict[str, Any]]] = None,
            model: Optional[str] = None,
            is_initial_prompt: bool = False,
            sub_agent: Optional[str] = None,
    ) -> AsyncGenerator[Message, None]:
        """Execute instruction using Claude Code Python SDK"""

        ui.info("Starting Claude SDK execution", "Claude SDK")
        ui.debug(f"Instruction: {instruction[:100]}...", "Claude SDK")
        ui.debug(f"Project path: {project_path}", "Claude SDK")
        ui.debug(f"Session ID: {session_id}", "Claude SDK")

        if log_callback:
            await log_callback("Starting execution...")

        # Determine project/session early and decide whether to reuse existing session
        try:
            project_id = (
                project_path.split("/")[-1] if "/" in project_path else project_path
            )
        except Exception:
            project_id = project_path
        # Compute effective model name for CLI
        cli_model = self._get_cli_model_name(model) or "claude-sonnet-4-5-20250929"
        agent_key = (sub_agent or "default").strip().lower()
        session_key = f"{project_id}::{agent_key}::{cli_model}"
        try:
            existing_session_id_early = await self.get_session_id(session_key)
        except Exception:
            existing_session_id_early = None

        last_meta = self._last_session_meta.get(session_key) or {}
        reuse_session = bool(
            existing_session_id_early and last_meta.get("model") == cli_model and not is_initial_prompt
        )
        if reuse_session:
            ui.info(f"Reusing Claude session without re-init (model: {cli_model}, agent: {agent_key})", "Claude SDK")
        else:
            ui.debug(
                f"Session init required (existing_session={bool(existing_session_id_early)}, last_model={last_meta.get('model')}, current_model={cli_model}, initial={is_initial_prompt}, agent={agent_key})",
                "Claude SDK",
            )

        # Update last-known session meta (model)
        self._last_session_meta[session_key] = {
            "model": cli_model,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Load system prompt (skip when reusing session)
        if not reuse_session:
            try:
                from app.services.claude_act import get_system_prompt

                # Use full system-prompt only for initial project setup; otherwise use core+design
                system_prompt = get_system_prompt(first_run=is_initial_prompt, sub_agent=sub_agent)
                ui.debug(f"System prompt loaded: {len(system_prompt)} chars", "Claude SDK")
                full_system_prompt = system_prompt
                trimmed_system_prompt = system_prompt
            except Exception as e:
                ui.error(f"Failed to load system prompt: {e}", "Claude SDK")
                full_system_prompt = (
                    "You are Claude Code, an AI coding assistant specialized in building modern web applications."
                )
                trimmed_system_prompt = full_system_prompt
        else:
            # When reusing session, don't reload prompts or pass them to options
            full_system_prompt = ""
            trimmed_system_prompt = ""

        # Enforce concise, frugal assistant style to reduce token usage
        concise_directive = (
            "\n\nStyle & efficiency rules:\n"
            "- Be concise; avoid long breakdowns.\n"
            "- Avoid step-by-step lists unless explicitly asked. Prefer direct, surgical edits.\n"
            "- Never paste long code in chat. Use Write/Edit/MultiEdit tools to apply changes and reply with one concise summary line.\n"
            "- Before reading files, use Glob/Grep to locate only the smallest necessary files.\n"
            "- Do not read or write in ignored paths (node_modules, .next, dist, coverage, *.lock, public/assets, large binaries).\n"
            "- If a read would exceed ~200 KB, stop and propose a narrower plan or chunk the work.\n"
            "- Maintain a concise change log in context/session-summary.md instead of repeating history in chat.\n"
            "- When referencing files in chat, show only the final filename (e.g., 'TodoForm.tsx').\n"
        )
        try:
            full_system_prompt = (full_system_prompt or "") + concise_directive
            trimmed_system_prompt = (trimmed_system_prompt or "") + concise_directive
        except Exception:
            pass


        # Provide a tiny repo map instead of large directory listings for initial prompts
        if is_initial_prompt:
            try:
                context_dir = os.path.join(project_path, "context")
                os.makedirs(context_dir, exist_ok=True)

                # Build a compact repo map (top-level dirs + notable files with sizes)
                repo_map = {"dirs": [], "notableFiles": [], "generated_at": datetime.utcnow().isoformat()}
                try:
                    entries = sorted(os.listdir(project_path))
                    ignore_names = {"node_modules", ".next", "dist", "build", "coverage", ".git", ".venv"}
                    for name in entries:
                        if name in ignore_names:
                            continue
                        full = os.path.join(project_path, name)
                        if os.path.isdir(full):
                            repo_map["dirs"].append(name)
                    # Cap dirs list to ~20 entries
                    repo_map["dirs"] = repo_map["dirs"][:20]
                except Exception:
                    pass

                notable = [
                    "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock",
                    "next.config.mjs", "next.config.js", "tailwind.config.ts", "tailwind.config.js",
                    "tsconfig.json", "README.md", ".env", ".env.example"
                ]
                for fname in notable:
                    p = os.path.join(project_path, fname)
                    try:
                        if os.path.isfile(p):
                            size = os.path.getsize(p)
                            repo_map["notableFiles"].append({"path": fname, "bytes": int(size)})
                    except Exception:
                        continue

                repo_map_path = os.path.join(context_dir, "repo-map.json")
                try:
                    with open(repo_map_path, "w", encoding="utf-8") as f:
                        json.dump(repo_map, f, ensure_ascii=False)
                    ui.info(f"Wrote compact repo map to context/repo-map.json", "Claude SDK")
                except Exception as write_err:
                    ui.warning(f"Failed to write repo map: {write_err}", "Claude SDK")

                # Ensure session-summary.md exists
                summary_path = os.path.join(context_dir, "session-summary.md")
                if not os.path.exists(summary_path):
                    try:
                        with open(summary_path, "w", encoding="utf-8") as f:
                            f.write("# Session Summary\n\n- Use this file to keep a concise log of work done (features, files touched, follow-ups).\n\n" \
                                    f"Created: {datetime.utcnow().isoformat()}\n")
                    except Exception:
                        pass

                # Add a tiny hint to the instruction
                hint = ("\n\n[context] A small repository map is available at context/repo-map.json. "
                        "If you need more detail, use Glob/Grep to drill into files; do not ask for or generate large listings. "
                        "Maintain a concise change log in context/session-summary.md.")
                instruction = instruction + hint
            except Exception as e:
                ui.warning(f"Failed to prepare compact repo context: {e}", "Claude SDK")

        session_settings_path = None
        base_settings = {}
        settings_dir = os.path.join(project_path, ".claude")
        settings_file_path = os.path.join(settings_dir, "settings.json")
        # Persist a minimal default settings.json if missing (non-destructive)
        try:
            if not os.path.exists(settings_file_path):
                os.makedirs(settings_dir, exist_ok=True)
                _persistent_defaults = {
                    "ignorePaths": [
                        "node_modules", ".next", "dist", "build", "coverage", ".git", "**/*.min.*", "**/*.map",
                        "public/assets/**", "**/*.lock", "**/*.svg", "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif"
                    ],
                    "maxReadBytes": 200000,
                    "maxToolReadsPerTurn": 30,
                    "preferDiffEdits": True,
                    "autoApplyEdits": True,
                }
                with open(settings_file_path, "w", encoding="utf-8") as f:
                    json.dump(_persistent_defaults, f, ensure_ascii=False, indent=2)
                ui.info("Created default .claude/settings.json with conservative limits", "Claude SDK")
        except Exception as _persist_err:
            ui.warning(f"Could not persist default .claude/settings.json: {_persist_err}", "Claude SDK")

        if not reuse_session:
            if os.path.exists(settings_file_path):
                try:
                    with open(settings_file_path, "r", encoding="utf-8") as settings_file:
                        loaded_settings = json.load(settings_file)
                        if isinstance(loaded_settings, dict):
                            base_settings = loaded_settings
                        else:
                            ui.warning("Existing Claude settings file is not a JSON object; ignoring it", "Claude SDK")
                except Exception as settings_error:
                    ui.warning(f"Failed to load existing Claude settings: {settings_error}", "Claude SDK")
            session_settings = dict(base_settings)

            # Inject conservative defaults to reduce token usage/tool noise
            default_settings = {
                "ignorePaths": [
                    "node_modules", ".next", "dist", "build", "coverage", ".git", "**/*.min.*", "**/*.map",
                    "public/assets/**", "**/*.lock", "**/*.svg", "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif"
                ],
                "maxReadBytes": 200000,
                "maxToolReadsPerTurn": 30,
                "preferDiffEdits": True,
                "autoApplyEdits": True,
            }
            # Merge defaults without overwriting explicit project settings
            for k, v in default_settings.items():
                if k not in session_settings:
                    session_settings[k] = v
                elif k == "ignorePaths":
                    try:
                        existing = set(session_settings.get("ignorePaths", []) or [])
                        for item in v:
                            if item not in existing:
                                existing.add(item)
                        session_settings["ignorePaths"] = list(existing)
                    except Exception:
                        session_settings["ignorePaths"] = v

            session_settings["customSystemPrompt"] = full_system_prompt
            try:
                temp_settings = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
                json.dump(session_settings, temp_settings, ensure_ascii=False)
                temp_settings.flush()
                temp_settings.close()
                session_settings_path = temp_settings.name
                ui.debug(f"Wrote temporary Claude settings to {session_settings_path}", "Claude SDK")
            except Exception as settings_write_error:
                ui.warning(f"Failed to create temporary settings file for Claude CLI: {settings_write_error}", "Claude SDK")
                session_settings_path = None
        else:
            ui.debug("Skipping settings file creation (reusing existing session)", "Claude SDK")

        # Configure tools based on initial prompt status
        if is_initial_prompt:
            # For initial prompts: use disallowed_tools to explicitly block TodoWrite
            allowed_tools = [
                "Read",
                "Write",
                "Edit",
                "MultiEdit",
                "Bash",
                "Glob",
                "Grep",
                "LS",
                "WebFetch",
                "WebSearch",
            ]
            disallowed_tools = ["TodoWrite"]

            ui.info(
                f"TodoWrite tool EXCLUDED via disallowed_tools (is_initial_prompt: {is_initial_prompt})",
                "Claude SDK",
            )
            ui.debug(f"Allowed tools: {allowed_tools}", "Claude SDK")
            ui.debug(f"Disallowed tools: {disallowed_tools}", "Claude SDK")

            # Configure Claude Code options with disallowed_tools
            option_kwargs = {
                "allowed_tools": allowed_tools,
                "disallowed_tools": disallowed_tools,
                "permission_mode": "bypassPermissions",
                "model": cli_model,
                "continue_conversation": True,
                "extra_args": {
                    "print": None,
                    "verbose": None,
                },
            }
            if session_settings_path:
                option_kwargs["settings"] = session_settings_path
            elif not reuse_session:
                option_kwargs["system_prompt"] = trimmed_system_prompt
            # When reusing session, avoid passing system_prompt/settings to prevent re-init
            options = ClaudeCodeOptions(**option_kwargs)
        else:
            # For non-initial prompts: include TodoWrite in allowed tools
            allowed_tools = [
                "Read",
                "Write",
                "Edit",
                "MultiEdit",
                "Bash",
                "Glob",
                "Grep",
                "LS",
                "WebFetch",
                "WebSearch",
                "TodoWrite",
            ]

            ui.info(
                f"TodoWrite tool INCLUDED (is_initial_prompt: {is_initial_prompt})",
                "Claude SDK",
            )
            ui.debug(f"Allowed tools: {allowed_tools}", "Claude SDK")

            # Configure Claude Code options without disallowed_tools
            option_kwargs = {
                "allowed_tools": allowed_tools,
                "permission_mode": "bypassPermissions",
                "model": cli_model,
                "continue_conversation": True,
                "extra_args": {
                    "print": None,
                    "verbose": None,
                },
            }
            if session_settings_path:
                option_kwargs["settings"] = session_settings_path
            elif not reuse_session:
                option_kwargs["system_prompt"] = trimmed_system_prompt
            # When reusing session, avoid passing system_prompt/settings to prevent re-init
            options = ClaudeCodeOptions(**option_kwargs)

        # Early resume if we already have a session id and plan to reuse
        try:
            if existing_session_id_early and not getattr(options, "resumeSessionId", None):
                options.resumeSessionId = existing_session_id_early
                ui.info(f"Resuming session: {existing_session_id_early}", "Claude SDK")
        except Exception:
            pass

        ui.info(f"Using model: {cli_model}", "Claude SDK")
        ui.debug(f"Project path: {project_path}", "Claude SDK")
        ui.debug(f"Instruction: {instruction[:100]}...", "Claude SDK")

        try:
            # Change to project directory
            original_cwd = os.getcwd()
            os.chdir(project_path)

            # Get project ID for session management
            project_id = (
                project_path.split("/")[-1] if "/" in project_path else project_path
            )
            existing_session_id = await self.get_session_id(session_key)

            # Update options with resume session if available
            if existing_session_id and not getattr(options, "resumeSessionId", None):
                options.resumeSessionId = existing_session_id
                ui.info(f"Resuming session: {existing_session_id}", "Claude SDK")

            try:
                async with ClaudeSDKClient(options=options) as client:
                    # Send initial query
                    await client.query(instruction)

                    # Stream responses and extract session_id
                    claude_session_id = None

                    async for message_obj in client.receive_messages():
                        # Import SDK types for isinstance checks
                        try:
                            from anthropic.claude_code.types import (
                                SystemMessage,
                                AssistantMessage,
                                UserMessage,
                                ResultMessage,
                            )
                        except ImportError:
                            try:
                                from claude_code_sdk.types import (
                                    SystemMessage,
                                    AssistantMessage,
                                    UserMessage,
                                    ResultMessage,
                                )
                            except ImportError:
                                # Fallback - check type name strings
                                SystemMessage = type(None)
                                AssistantMessage = type(None)
                                UserMessage = type(None)
                                ResultMessage = type(None)

                        # Handle SystemMessage for session_id extraction
                        if (
                                isinstance(message_obj, SystemMessage)
                                or "SystemMessage" in str(type(message_obj))
                        ):
                            # Extract session_id if available
                            if (
                                    hasattr(message_obj, "session_id")
                                    and message_obj.session_id
                            ):
                                claude_session_id = message_obj.session_id
                                await self.set_session_id(
                                    session_key, claude_session_id
                                )

                            # Send init message (hidden from UI)
                            init_message = Message(
                                id=str(uuid.uuid4()),
                                project_id=project_path,
                                role="system",
                                message_type="system",
                                content=f"Claude Code SDK initialized (Model: {cli_model})",
                                metadata_json={
                                    "cli_type": self.cli_type.value,
                                    "mode": "SDK",
                                    "model": cli_model,
                                    "session_id": getattr(
                                        message_obj, "session_id", None
                                    ),
                                    "hidden_from_ui": True,
                                },
                                session_id=session_id,
                                created_at=datetime.utcnow(),
                            )
                            yield init_message

                        # Handle AssistantMessage (complete messages)
                        elif (
                                isinstance(message_obj, AssistantMessage)
                                or "AssistantMessage" in str(type(message_obj))
                        ):
                            content = ""

                            # Process content - AssistantMessage has content: list[ContentBlock]
                            if hasattr(message_obj, "content") and isinstance(
                                    message_obj.content, list
                            ):
                                for block in message_obj.content:
                                    # Import block types for comparison
                                    from claude_code_sdk.types import (
                                        TextBlock,
                                        ToolUseBlock,
                                        ToolResultBlock,
                                    )

                                    if isinstance(block, TextBlock):
                                        # TextBlock has 'text' attribute
                                        content += block.text
                                    elif isinstance(block, ToolUseBlock):
                                        # ToolUseBlock has 'id', 'name', 'input' attributes
                                        tool_name = block.name
                                        tool_input = block.input
                                        tool_id = block.id
                                        summary = self._create_tool_summary(
                                            tool_name, tool_input
                                        )

                                        # Yield tool use message immediately
                                        tool_message = Message(
                                            id=str(uuid.uuid4()),
                                            project_id=project_path,
                                            role="assistant",
                                            message_type="tool_use",
                                            content=summary,
                                            metadata_json={
                                                "cli_type": self.cli_type.value,
                                                "mode": "SDK",
                                                "tool_name": tool_name,
                                                "tool_input": tool_input,
                                                "tool_id": tool_id,
                                            },
                                            session_id=session_id,
                                            created_at=datetime.utcnow(),
                                        )
                                        # Display clean tool usage like Claude Code
                                        tool_display = self._get_clean_tool_display(
                                            tool_name, tool_input
                                        )
                                        ui.info(tool_display, "")
                                        yield tool_message
                                    elif isinstance(block, ToolResultBlock):
                                        # Handle tool result blocks if needed
                                        pass

                            # Yield complete assistant text message if there's text content
                            if content and content.strip():
                                text_message = Message(
                                    id=str(uuid.uuid4()),
                                    project_id=project_path,
                                    role="assistant",
                                    message_type="chat",
                                    content=content.strip(),
                                    metadata_json={
                                        "cli_type": self.cli_type.value,
                                        "mode": "SDK",
                                    },
                                    session_id=session_id,
                                    created_at=datetime.utcnow(),
                                )
                                yield text_message

                        # Handle UserMessage (tool results, etc.)
                        elif (
                                isinstance(message_obj, UserMessage)
                                or "UserMessage" in str(type(message_obj))
                        ):
                            # UserMessage has content: str according to types.py
                            # UserMessages are typically tool results - we don't need to show them
                            pass

                        # Handle ResultMessage (final session completion)
                        elif (
                                isinstance(message_obj, ResultMessage)
                                or "ResultMessage" in str(type(message_obj))
                                or (
                                        hasattr(message_obj, "type")
                                        and getattr(message_obj, "type", None) == "result"
                                )
                        ):
                            ui.success(
                                f"Session completed in {getattr(message_obj, 'duration_ms', 0)}ms",
                                "Claude SDK",
                            )

                            # Create internal result message (hidden from UI)
                            result_message = Message(
                                id=str(uuid.uuid4()),
                                project_id=project_path,
                                role="system",
                                message_type="result",
                                content=(
                                    f"Session completed in {getattr(message_obj, 'duration_ms', 0)}ms"
                                ),
                                metadata_json={
                                    "cli_type": self.cli_type.value,
                                    "mode": "SDK",
                                    "duration_ms": getattr(
                                        message_obj, "duration_ms", 0
                                    ),
                                    "duration_api_ms": getattr(
                                        message_obj, "duration_api_ms", 0
                                    ),
                                    "total_cost_usd": getattr(
                                        message_obj, "total_cost_usd", 0
                                    ),
                                    "num_turns": getattr(message_obj, "num_turns", 0),
                                    "is_error": getattr(message_obj, "is_error", False),
                                    "subtype": getattr(message_obj, "subtype", None),
                                    "session_id": getattr(
                                        message_obj, "session_id", None
                                    ),
                                    "hidden_from_ui": True,  # Don't show to user
                                },
                                session_id=session_id,
                                created_at=datetime.utcnow(),
                            )
                            yield result_message
                            break

                        # Handle unknown message types
                        else:
                            ui.debug(
                                f"Unknown message type: {type(message_obj)}",
                                "Claude SDK",
                            )

            finally:
                try:
                    if session_settings_path and os.path.exists(session_settings_path):
                        os.remove(session_settings_path)
                except Exception as cleanup_error:
                    ui.debug(f"Failed to remove temporary settings file {session_settings_path}: {cleanup_error}",
                             "Claude SDK")
                # Restore original working directory
                os.chdir(original_cwd)

        except Exception as e:
            ui.error(f"Exception occurred: {str(e)}", "Claude SDK")
            if log_callback:
                await log_callback(f"Claude SDK Exception: {str(e)}")
            raise

    async def get_session_id(self, project_id: str) -> Optional[str]:
        """Get current session ID for project from database"""
        try:
            # Try to get from database if available (we'll need to pass db session)
            return self.session_mapping.get(project_id)
        except Exception as e:
            ui.warning(f"Failed to get session ID from DB: {e}", "Claude SDK")
            return self.session_mapping.get(project_id)

    async def set_session_id(self, project_id: str, session_id: str) -> None:
        """Set session ID for project in database and memory"""
        try:
            # Store in memory as fallback
            self.session_mapping[project_id] = session_id
            ui.debug(
                f"Session ID stored for project {project_id}", "Claude SDK"
            )
        except Exception as e:
            ui.warning(f"Failed to save session ID: {e}", "Claude SDK")
            # Fallback to memory storage
            self.session_mapping[project_id] = session_id


__all__ = ["ClaudeCodeCLI"]
