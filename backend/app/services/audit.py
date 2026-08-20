"""Security audit trail (Phase 10.2). Every sensitive action leaves a row:
who, what, when, and a JSON detail. Best-effort by design — an audit
failure must never break the action it records (it logs instead)."""
from __future__ import annotations

import logging

import psycopg
from psycopg.types.json import Json

from app.config import get_settings
from app.db.app_repo import _dumps

logger = logging.getLogger("supplyscope.audit")

_DDL = """
CREATE TABLE IF NOT EXISTS app.audit_log (
    audit_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    integer,
    action     text NOT NULL,
    detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON app.audit_log (created_at DESC);
"""


def ensure_ddl() -> None:
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute(_DDL)


def audit(action: str, user_id: int | None = None, **detail) -> None:
    try:
        with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
            c.execute(
                "INSERT INTO app.audit_log (user_id, action, detail) "
                "VALUES (%s, %s, %s)",
                (user_id, action, Json(detail, dumps=_dumps)))
    except psycopg.Error:
        logger.exception("audit write failed for %s", action)


def recent(limit: int = 100, action: str | None = None) -> list[dict]:
    from psycopg.rows import dict_row
    with psycopg.connect(get_settings().app_dsn, row_factory=dict_row) as c:
        ensure_ddl()
        if action:
            return c.execute(
                "SELECT * FROM app.audit_log WHERE action = %s "
                "ORDER BY audit_id DESC LIMIT %s", (action, limit)).fetchall()
        return c.execute("SELECT * FROM app.audit_log "
                         "ORDER BY audit_id DESC LIMIT %s", (limit,)).fetchall()
