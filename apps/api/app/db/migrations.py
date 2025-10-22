"""Database migrations module for SQLite."""

import logging
from typing import Optional, Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    # SQLite pragma to list columns
    res = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in res)


def _index_exists(conn, index_name: str) -> bool:
    res = conn.execute(text("PRAGMA index_list(projects)")).fetchall()
    # row[1] is index name
    return any(row[1] == index_name for row in res)


def run_sqlite_migrations(engine_or_path: Optional[Any] = None) -> None:
    """
    Run SQLite database migrations.
    Accepts an SQLAlchemy Engine (preferred) or a DB path for logging only.
    Skips execution when a non-SQLite engine is provided.
    """
    try:
        if isinstance(engine_or_path, Engine):
            engine: Engine = engine_or_path
            # Skip when not using SQLite
            if getattr(engine, "dialect", None) and getattr(engine.dialect, "name", "") != "sqlite":
                logger.info(f"[migrations] Skipping SQLite migrations for non-sqlite engine: {engine.dialect.name}")
                return
            with engine.begin() as conn:
                # 1) Add owner_id column to projects if missing
                if not _column_exists(conn, "projects", "owner_id"):
                    logger.info("[migrations] Adding owner_id column to projects table")
                    conn.execute(text("ALTER TABLE projects ADD COLUMN owner_id TEXT"))
                # 2) Create index on owner_id if missing
                if not _index_exists(conn, "ix_projects_owner_id"):
                    logger.info("[migrations] Creating index ix_projects_owner_id on projects.owner_id")
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_owner_id ON projects(owner_id)"))
        else:
            if engine_or_path:
                logger.info(f"Running migrations for SQLite database at: {engine_or_path}")
            else:
                logger.info("Running migrations for in-memory SQLite database")
    except Exception as e:
        logger.error(f"SQLite migrations failed: {e}")
        # Don't crash app on migration failure in dev; just log
