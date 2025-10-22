import sys

from app.core.terminal_ui import TerminalUIHandler

import logging


def configure_logging() -> None:
    """Configure logging with clean terminal UI.

    Respects DEBUG env var (true/1/yes/on) to enable verbose logs.
    In non-debug mode, only warnings and above are shown to avoid noise.
    """
    import os
    debug_env = os.getenv("DEBUG", "false").strip().lower()
    debug_enabled = debug_env in ("1", "true", "yes", "on")

    # Clear existing handlers
    root = logging.getLogger()
    root.handlers.clear()

    # Add our custom terminal UI handler
    terminal_handler = TerminalUIHandler()
    terminal_handler.setLevel(logging.DEBUG if debug_enabled else logging.WARNING)

    # Add standard handler for stdout when debugging
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)

    root.setLevel(logging.DEBUG if debug_enabled else logging.WARNING)
    root.addHandler(terminal_handler)

    if debug_enabled:
        root.addHandler(stream_handler)

    # Quiet noisy third-party loggers in non-debug mode
    if not debug_enabled:
        for noisy in ("uvicorn", "uvicorn.access", "sqlalchemy.engine", "watchfiles"):
            try:
                logging.getLogger(noisy).setLevel(logging.WARNING)
            except Exception:
                pass
