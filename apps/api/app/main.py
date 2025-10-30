from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from app.api.projects import router as projects_router
from app.api.repo import router as repo_router
from app.api.commits import router as commits_router
from app.api.env import router as env_router
from app.api.assets import router as assets_router
from app.api.chat import router as chat_router
from app.api.tokens import router as tokens_router
from app.api.settings import router as settings_router
from app.api.project_services import router as project_services_router
from app.api.github import router as github_router
from app.api.vercel import router as vercel_router
from app.api.billing import router as billing_router
from app.api.privacy import router as privacy_router
from app.api.users import router as users_router
from app.core.logging import configure_logging
from app.core.terminal_ui import ui
from sqlalchemy import inspect
from app.db.base import Base
import app.models  # noqa: F401 ensures models are imported for metadata
from app.db.session import engine
from app.db.migrations import run_sqlite_migrations
import os
import time
import socket
from urllib.parse import urlparse
from pathlib import Path
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from app.core.config import settings

configure_logging()
from app.core.error_handlers import register_exception_handlers

app = FastAPI(title="Vrabby API")
register_exception_handlers(app)
# TODO: Add tenant resolution middleware based on request host (domain → tenant_id) and propagate via request.state.tenant_id

# Middleware to suppress logging for specific endpoints
class LogFilterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Suppress logging for polling endpoints
        if "/requests/active" in request.url.path:
            import logging
            logger = logging.getLogger("uvicorn.access")
            original_disabled = logger.disabled
            logger.disabled = True
            try:
                response = await call_next(request)
            finally:
                logger.disabled = original_disabled
        else:
            response = await call_next(request)
        return response

# Rate limiting middleware (in-memory)
import threading, base64, json as _json
from time import time as _time

# TODO: Replace in-memory rate limiter with per-tenant, persistent store (e.g., Redis), using tenant context from middleware
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.lock = threading.Lock()
        self.buckets = {}  # key -> {"minute": (window_start_ts, count), "day": (window_start_ts, count)}

    def _tenant_id(self, request: Request) -> str:
        # Derive tenant from explicit header or from Host (subdomain)
        tid = (request.headers.get("X-Tenant-ID") or "").strip()
        if tid:
            return tid
        host = (request.headers.get("host") or request.headers.get("Host") or "").split(":")[0]
        # naive subdomain parsing: sub.domain.tld -> sub
        if host and host.count(".") >= 2:
            return host.split(".")[0]
        return "default"

    def _key_for(self, request: Request) -> str:
        # Prefer Supabase user id from unverified JWT for lightweight keying
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        tenant = self._tenant_id(request)
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            parts = token.split('.')
            if len(parts) >= 2:
                try:
                    payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
                    payload = _json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
                    sub = payload.get('sub') or payload.get('user_id')
                    if sub:
                        return f"t:{tenant}|uid:{sub}"
                except Exception:
                    pass
        # Fallback to IP
        ip = request.client.host if request.client else 'unknown'
        return f"t:{tenant}|ip:{ip}"

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        key = self._key_for(request)
        now = _time()
        minute_window = 60.0
        day_window = 86400.0

        # Method-aware limits (allow higher read throughput for GET)
        is_get = (request.method.upper() == 'GET')
        base_min_limit = settings.rate_limit_per_min
        m_limit_effective = base_min_limit * (5 if is_get else 1)
        d_limit = settings.rate_limit_per_day

        with self.lock:
            data = self.buckets.get(key, {"minute": (now, 0), "day": (now, 0)})
            m_start, m_count = data["minute"]
            d_start, d_count = data["day"]
            # Reset windows if expired
            if now - m_start >= minute_window:
                m_start, m_count = now, 0
            if now - d_start >= day_window:
                d_start, d_count = now, 0
            # Apply limits
            if m_count + 1 > m_limit_effective or d_count + 1 > d_limit:
                # Return 429 with headers
                from starlette.responses import JSONResponse
                retry_after = int(max(1, minute_window - (now - m_start))) if m_count + 1 > m_limit_effective else int(max(1, day_window - (now - d_start)))
                headers = {
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit-Minute": str(m_limit_effective),
                    "X-RateLimit-Remaining-Minute": str(max(0, int(m_limit_effective - m_count))),
                    "X-RateLimit-Limit-Day": str(d_limit),
                    "X-RateLimit-Remaining-Day": str(max(0, d_limit - d_count)),
                }
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429, headers=headers)
            # Increment and store
            m_count += 1
            d_count += 1
            data["minute"] = (m_start, m_count)
            data["day"] = (d_start, d_count)
            self.buckets[key] = data
        response = await call_next(request)
        # Expose remaining counts
        try:
            response.headers["X-RateLimit-Limit-Minute"] = str(m_limit_effective)
            response.headers["X-RateLimit-Limit-Day"] = str(d_limit)
        except Exception:
            pass
        return response

# CORS should be outermost so it can attach headers to all responses, including errors
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(LogFilterMiddleware)
app.add_middleware(RateLimitMiddleware)

# Routers
app.include_router(projects_router, prefix="/api/projects")
app.include_router(repo_router)
app.include_router(commits_router)
app.include_router(env_router)
app.include_router(assets_router)
app.include_router(chat_router, prefix="/api/chat")  # Unified chat API (includes WebSocket and ACT)
app.include_router(tokens_router)  # Service tokens API
app.include_router(settings_router)  # Settings API
app.include_router(project_services_router)  # Project services API
app.include_router(github_router)  # GitHub integration API
app.include_router(vercel_router)  # Vercel integration API
app.include_router(billing_router)  # Billing & credits API
app.include_router(privacy_router)  # GDPR Privacy API
app.include_router(users_router)  # Users profile API


@app.get("/health")
def health():
    # Health check with short cache to reduce overhead
    from starlette.responses import JSONResponse
    return JSONResponse({"ok": True}, headers={"Cache-Control": "public, max-age=60"})


@app.on_event("startup")
def on_startup() -> None:
    """API startup: run DB migrations with retries and helpful diagnostics."""
    # Control auto-migrations via env (default: on)
    auto_migrate = (os.getenv("DB_MIGRATIONS_ON_STARTUP", "1").strip().lower() in ("1", "true", "yes", "on"))
    max_retries = int(os.getenv("DB_MIGRATIONS_MAX_RETRIES", "5") or 5)
    retry_delay = float(os.getenv("DB_MIGRATIONS_RETRY_DELAY_SEC", "3") or 3)

    if not auto_migrate:
        ui.info("Skipping database migrations on startup (DB_MIGRATIONS_ON_STARTUP=0)")
    else:
        # Basic DNS precheck for clearer errors
        try:
            parsed = urlparse(settings.database_url)
            host = parsed.hostname
            port = parsed.port or 5432
            if not host:
                ui.error("Invalid DATABASE_URL: host is missing", "DB")
                raise RuntimeError("DATABASE_URL host missing")
            # Try to resolve host
            try:
                socket.getaddrinfo(host, port)
            except Exception as e:
                ui.error(
                    f"Cannot resolve database host '{host}'. Check internet/VPN/DNS and DATABASE_URL. Error: {e}",
                    "DB"
                )
                # Continue to retry loop below which will still attempt connection
        except Exception:
            # If parsing fails, let alembic throw a more detailed error later
            pass

        ui.info("Running database migrations")
        alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
        alembic_cfg = AlembicConfig(str(alembic_ini))
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

        last_err: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                alembic_command.upgrade(alembic_cfg, "head")
                ui.success("Database migrations applied")
                last_err = None
                break
            except Exception as e:
                last_err = e
                ui.error(f"Alembic migration attempt {attempt}/{max_retries} failed: {e}", "DB")
                if attempt < max_retries:
                    time.sleep(retry_delay)
        if last_err:
            ui.error(
                "Alembic migration failed after retries. "
                "If this is a temporary network/DNS issue, try again. "
                "To skip auto-migrations for frontend-only development, set DB_MIGRATIONS_ON_STARTUP=0.",
                "DB",
            )
            raise last_err

    # Run lightweight SQLite migrations for additive changes (no-op on Postgres)
    run_sqlite_migrations(engine)

    # Show available endpoints
    ui.info("API server ready")
    ui.panel(
        "WebSocket: /api/chat/{project_id}\nREST API: /api/projects, /api/chat, /api/github, /api/vercel",
        title="Available Endpoints",
        style="green",
    )

    # Display ASCII logo after all initialization is complete
    ui.ascii_logo()

    # Warm-up Claude SDK/CLI in the background to reduce first-response latency
    try:
        def _warmup():
            try:
                import asyncio
                from app.services.cli.adapters.claude_code import ClaudeCodeCLI
                async def _run():
                    try:
                        await asyncio.wait_for(ClaudeCodeCLI().check_availability(), timeout=10)
                        ui.success("Claude Code initialized", "AI")
                    except asyncio.TimeoutError:
                        ui.warn("Claude Code warm-up timed out (will initialize on first use)", "AI")
                asyncio.run(_run())
            except Exception as e:
                try:
                    ui.warn(f"Claude Code not ready: {e}", "AI")
                except Exception:
                    pass
        threading.Thread(target=_warmup, daemon=True).start()
    except Exception:
        pass

    # Show environment info
    env_info = {
        "Environment": os.getenv("ENVIRONMENT", "development"),
        "Debug": os.getenv("DEBUG", "false"),
        "Port": os.getenv("PORT", "8000"),
    }
    ui.status_line(env_info)
