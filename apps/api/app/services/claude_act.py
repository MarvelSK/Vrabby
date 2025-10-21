import os
from typing import Tuple, Optional, Callable, Dict, List
import json
from datetime import datetime
from pathlib import Path

from claude_code_sdk import query, ClaudeCodeOptions
from claude_code_sdk.types import (
    Message, AssistantMessage, SystemMessage, ResultMessage,
    TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock
)

# Prefer newest model by env; fallback to stable Claude Sonnet 4.5
DEFAULT_MODEL = os.getenv("CLAUDE_CODE_MODEL", "claude-sonnet-4-5-20250929")

# Cache for system prompt variants
_PROMPT_CACHE: Dict[str, str] = {}

# ==========================================================
# 🧠 PROMPT MANAGEMENT (core / design / build)
# ==========================================================

def _prompt_dir() -> Path:
    """Return canonical prompt directory."""
    return Path(__file__).resolve().parent.parent / "prompt"


def _read_file_safe(p: Path) -> Optional[str]:
    try:
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"❌ Could not read prompt file {p}: {e}")
    return None


def _find_prompt_variants() -> Dict[str, Path]:
    """
    Locate system-core.md, system-design.md, system-build.md with fallbacks.
    """
    base = _prompt_dir()
    variants = {
        "core": [
            base / "system-core.md", base / "system_core.md", base / "core.md"
        ],
        "design": [
            base / "system-design.md", base / "system_design.md", base / "design.md"
        ],
        "build": [
            base / "system-build.md", base / "system_build.md", base / "build.md"
        ],
        "legacy_single": [
            base / "system-prompt.md", base / "system_prompt.md"
        ]
    }

    resolved: Dict[str, Path] = {}
    for key, paths in variants.items():
        for p in paths:
            if p.exists():
                resolved[key] = p
                break
    return resolved


def _compose_system_prompt(first_run: bool) -> str:
    """
    Compose the effective system prompt dynamically:
      • core always
      • design only for first_run (initial project creation)
      • build always
    Falls back to legacy or minimal prompt if none found.
    """
    cache_key = f"first_run={first_run}"
    if cache_key in _PROMPT_CACHE:
        return _PROMPT_CACHE[cache_key]

    resolved = _find_prompt_variants()
    parts: List[str] = []

    core_txt = _read_file_safe(resolved.get("core", Path()))
    design_txt = _read_file_safe(resolved.get("design", Path())) if first_run else None
    build_txt = _read_file_safe(resolved.get("build", Path()))

    if core_txt or design_txt or build_txt:
        if core_txt:
            parts.append(core_txt)
        if first_run and design_txt:
            parts.append("\n\n---\n\n" + design_txt)
        if build_txt:
            parts.append("\n\n---\n\n" + build_txt)

        composed = "\n".join(parts).strip()
        print(f"✅ Loaded system prompts (core{' + design' if first_run and design_txt else ''} + build)")
        _PROMPT_CACHE[cache_key] = composed
        return composed

    # Fallback: use legacy single file
    legacy_file = resolved.get("legacy_single")
    if legacy_file:
        txt = _read_file_safe(legacy_file)
        if txt:
            print("⚠️  Using legacy system-prompt.md fallback")
            _PROMPT_CACHE[cache_key] = txt
            return txt

    # Final fallback: hardcoded minimal prompt
    fallback = (
        "You are Vrabby, an advanced AI coding assistant created by Marek Vrábel, "
        "founder of MHost.sk. You specialize in building modern fullstack web applications "
        "with high-quality code, performance, and design. Use Next.js, TypeScript, and Tailwind "
        "best practices. Maintain clarity, accessibility, and production-readiness."
    )
    print("🛟 Using minimal fallback system prompt (no files found)")
    _PROMPT_CACHE[cache_key] = fallback
    return fallback


def get_system_prompt(first_run: bool = False) -> str:
    """Public accessor for dynamic prompt composition."""
    return _compose_system_prompt(first_run)


def get_initial_system_prompt() -> str:
    """Used for project creation — includes design prompt too."""
    return get_system_prompt(first_run=True)


# ✅ Backward compatibility (for imports in system_prompt.py)
def load_system_prompt(force_reload: bool = False) -> str:
    if force_reload:
        _PROMPT_CACHE.clear()
    return get_system_prompt(False)


# ==========================================================
# 🧩 TOOL SUMMARY HELPERS
# ==========================================================

def extract_tool_summary(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Read":
        return f"📖 Reading: {tool_input.get('file_path', 'unknown')}"
    elif tool_name == "Write":
        return f"✏️ Writing: {tool_input.get('file_path', 'unknown')}"
    elif tool_name in {"Edit", "MultiEdit"}:
        return f"🔧 Editing: {tool_input.get('file_path', 'unknown')}"
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"💻 Running: {cmd[:60]}{'...' if len(cmd) > 60 else ''}"
    elif tool_name == "Glob":
        return f"🔍 Searching: {tool_input.get('pattern', 'unknown')}"
    elif tool_name == "Grep":
        return f"🔎 Grepping: {tool_input.get('pattern', 'unknown')}"
    elif tool_name == "LS":
        return f"📁 Listing: {tool_input.get('path', 'current dir')}"
    elif tool_name == "WebFetch":
        return f"🌐 Fetching: {tool_input.get('url', 'unknown')}"
    elif tool_name == "TodoWrite":
        return "📝 Managing todos"
    return f"🔧 Using {tool_name}"


# ==========================================================
# 🚀 MAIN EXECUTION WITH STREAMING
# ==========================================================

async def generate_diff_with_logging(
        instruction: str,
        allow_globs: list[str],
        repo_path: str,
        log_callback: Optional[Callable] = None,
        resume_session_id: Optional[str] = None,
        system_prompt: Optional[str] = None
) -> Tuple[str, str, Optional[str]]:
    """
    Executes Claude Code SDK with live stream + log callback.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️ Running in local mode — ANTHROPIC_API_KEY not set")

    is_first_run = resume_session_id is None

    user_prompt = (
        f"Task: {instruction}\n\n"
        "Implement the requested changes to this Next.js project. "
        "After completing, summarize using:\n"
        "<COMMIT_MSG>commit message</COMMIT_MSG>\n"
        "<SUMMARY>summary of changes</SUMMARY>"
    )

    effective_prompt = (
        system_prompt.strip()
        if system_prompt
        else get_system_prompt(first_run=is_first_run)
    )

    options = ClaudeCodeOptions(
        cwd=repo_path,
        allowed_tools=["Read", "Write", "Edit", "MultiEdit", "Bash", "Glob", "Grep", "LS"],
        permission_mode="acceptEdits",
        system_prompt=effective_prompt,
        model=DEFAULT_MODEL,
        resume=resume_session_id,
    )

    response_text = ""
    messages_received: List[str] = []
    pending_tools = {}
    current_session_id = None
    start_time = datetime.now()

    try:
        print(f"🎯 Starting Claude Code with: {instruction[:80]}...")
        message_count = 0
        if log_callback:
            await log_callback("text", {"content": "🚀 Starting Claude Code execution..."})

        async for message in query(prompt=user_prompt, options=options):
            message_count += 1
            messages_received.append(message)

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
                        if log_callback:
                            await log_callback("text", {"content": block.text})

                    elif isinstance(block, ThinkingBlock):
                        if log_callback:
                            t = block.thinking
                            await log_callback("thinking", {
                                "content": (t[:200] + "...") if len(t) > 200 else t
                            })

                    elif isinstance(block, ToolUseBlock):
                        pending_tools[block.id] = {
                            "name": block.name,
                            "input": block.input,
                            "summary": extract_tool_summary(block.name, block.input),
                        }
                        if log_callback:
                            await log_callback("tool_start", pending_tools[block.id])

                    elif isinstance(block, ToolResultBlock):
                        tool_info = pending_tools.pop(block.tool_use_id, {})
                        if log_callback:
                            await log_callback("tool_result", {
                                "tool_name": tool_info.get("name"),
                                "summary": tool_info.get("summary"),
                                "is_error": block.is_error or False,
                                "content": str(block.content)[:400],
                            })

            elif isinstance(message, ResultMessage):
                if hasattr(message, "session_id") and message.session_id:
                    current_session_id = message.session_id
                    print(f"🧩 Session ID: {current_session_id}")

                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                if log_callback:
                    await log_callback("result", {
                        "duration_ms": duration_ms,
                        "api_duration_ms": message.duration_api_ms,
                        "turns": message.num_turns,
                        "cost_usd": message.total_cost_usd,
                        "is_error": message.is_error,
                        "session_id": current_session_id,
                    })

    except Exception as exc:
        print(f"❌ Claude Code SDK Exception: {exc}")
        if log_callback:
            await log_callback("error", {"message": str(exc)})
        raise RuntimeError(f"Claude Code SDK failed: {exc}") from exc

    print(f"✅ Claude Code completed — {message_count} messages received.")

    if message_count == 0:
        response_text = (
            f"I understand you want to: {instruction}\n\n"
            "But Claude Code SDK might not be configured correctly. "
            "Ensure CLI or ANTHROPIC_API_KEY is set."
        )

    # Parse commit message and summary
    commit_msg = ""
    if "<COMMIT_MSG>" in response_text and "</COMMIT_MSG>" in response_text:
        commit_msg = response_text.split("<COMMIT_MSG>", 1)[1].split("</COMMIT_MSG>", 1)[0].strip()
    if not commit_msg:
        commit_msg = instruction[:72]

    diff_summary = "Changes applied via Claude Code"
    if "<SUMMARY>" in response_text and "</SUMMARY>" in response_text:
        diff_summary = response_text.split("<SUMMARY>", 1)[1].split("</SUMMARY>", 1)[0].strip()

    return commit_msg, diff_summary, current_session_id


__all__ = [
    "get_system_prompt",
    "get_initial_system_prompt",
    "load_system_prompt",
    "generate_diff_with_logging",
]
