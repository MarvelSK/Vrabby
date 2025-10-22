from pydantic import BaseModel
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


def normalize_database_url(raw_url: str) -> str:
    """
    Accepts common Postgres/Supabase URI forms and returns a SQLAlchemy-compatible URL.
    - Supports postgres:// and postgresql:// and adds the psycopg2 driver automatically
    - Ensures sslmode=require for Supabase hosts when not provided
    - Leaves non-Postgres URLs unchanged
    """
    if not raw_url:
        return ""
    url = raw_url.strip()

    # Normalize legacy postgres:// to postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    parsed = urlparse(url)
    scheme = parsed.scheme or ""

    # Only handle Postgres-like schemes
    base_scheme = scheme.split("+", 1)[0]
    if base_scheme not in ("postgresql", "postgres"):
        return url  # not a Postgres URL

    # Ensure sslmode=require for Supabase hosts if missing
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    host = parsed.hostname or ""
    if host.endswith(".supabase.co") and "sslmode" not in {k.lower() for k in query_items.keys()}:
        query_items["sslmode"] = "require"

    # Produce a SQLAlchemy-friendly URL; include explicit driver for clarity
    new_scheme = "postgresql+psycopg2"
    new_query = urlencode(query_items)
    normalized = urlunparse((
        new_scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))
    return normalized


def find_project_root() -> Path:
    """
    Find the project root directory by looking for specific marker files.
    This ensures consistent behavior regardless of where the API is executed from.
    """
    current_path = Path(__file__).resolve()
    
    # Start from current file and go up
    for parent in [current_path] + list(current_path.parents):
        # Check if this directory has both apps/ and Makefile (project root indicators)
        if (parent / 'apps').is_dir() and (parent / 'Makefile').exists():
            return parent
    
    # Fallback: navigate up from apps/api to project root
    # Current path is likely: /project-root/apps/api/app/core/config.py
    # So we need to go up 4 levels: config.py -> core -> app -> api -> apps -> project-root
    api_dir = current_path.parent.parent.parent  # /project-root/apps/api
    if api_dir.name == 'api' and api_dir.parent.name == 'apps':
        return api_dir.parent.parent  # /project-root
    
    # Last resort: current working directory
    return Path.cwd()


# Get project root once at module load
PROJECT_ROOT = find_project_root()

# Read raw DB URL from multiple possible envs
_RAW_DB_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("SUPABASE_DB_URL")
    or os.getenv("SUPABASE_DB_URI")
    or ""
)


class Settings(BaseModel):
    api_port: int = int(os.getenv("API_PORT", "8080"))
    
    # Database URL (Supabase Postgres recommended)
    # Accept plain postgres/postgresql URIs and normalize for SQLAlchemy engine
    database_url: str = normalize_database_url(_RAW_DB_URL)
    
    # Use project root relative paths
    projects_root: str = os.getenv("PROJECTS_ROOT", str(PROJECT_ROOT / "data" / "projects"))
    projects_root_host: str = os.getenv("PROJECTS_ROOT_HOST", os.getenv("PROJECTS_ROOT", str(PROJECT_ROOT / "data" / "projects")))
    
    preview_port_start: int = int(os.getenv("PREVIEW_PORT_START", "3100"))
    preview_port_end: int = int(os.getenv("PREVIEW_PORT_END", "3999"))

    # CORS configuration
    web_port_env: str = os.getenv("WEB_PORT", "3000")
    default_origin: str = os.getenv("DEFAULT_WEB_ORIGIN", f"http://localhost:{web_port_env}")
    allowed_origins_csv: str = os.getenv("ALLOWED_ORIGINS", default_origin)
    allowed_origins: list[str] = [o.strip() for o in allowed_origins_csv.split(",") if o.strip()]

    # Supabase Auth (JWKS)
    supabase_project_url: str | None = os.getenv("SUPABASE_PROJECT_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_jwks_url: str | None = os.getenv("SUPABASE_JWKS_URL") or (
        (os.getenv("SUPABASE_PROJECT_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")) and f"{(os.getenv('SUPABASE_PROJECT_URL') or os.getenv('NEXT_PUBLIC_SUPABASE_URL')).rstrip('/')}/auth/v1/keys"
    )

    # Stripe Billing
    stripe_secret_key: str | None = os.getenv("STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = os.getenv("STRIPE_WEBHOOK_SECRET")
    stripe_price_sub_monthly: str | None = os.getenv("STRIPE_PRICE_SUB_MONTHLY")  # recurring plan price id
    stripe_price_credits: str | None = os.getenv("STRIPE_PRICE_CREDITS")  # one-time credits pack price id
    subscription_credits_per_period: int = int(os.getenv("SUBSCRIPTION_CREDITS_PER_PERIOD", "100"))
    purchase_credits_per_unit: int = int(os.getenv("PURCHASE_CREDITS_PER_UNIT", "500"))
    free_credits_on_signup: int = int(os.getenv("FREE_CREDITS_ON_SIGNUP", "20"))

    # Token-based billing settings
    tokens_per_credit: int = int(os.getenv("TOKENS_PER_CREDIT", "1000"))

    # Rate limits
    rate_limit_per_min: int = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
    rate_limit_burst: int = int(os.getenv("RATE_LIMIT_BURST", "60"))
    rate_limit_per_day: int = int(os.getenv("RATE_LIMIT_PER_DAY", "5000"))

    # Sandbox settings
    sandbox_enabled: bool = (os.getenv("SANDBOX_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on"))
    sandbox_docker_image: str = os.getenv("SANDBOX_DOCKER_IMAGE", "node:20")
    sandbox_cpu: str = os.getenv("SANDBOX_CPU", "1.0")
    sandbox_memory: str = os.getenv("SANDBOX_MEMORY", "1g")
    sandbox_timeout_sec: int = int(os.getenv("SANDBOX_TIMEOUT_SEC", "600"))


settings = Settings()

# Enforce Postgres connection string presence
if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL not configured. Set to your Supabase Postgres connection string (e.g., postgresql://user:pass@host:5432/db?sslmode=require)."
    )