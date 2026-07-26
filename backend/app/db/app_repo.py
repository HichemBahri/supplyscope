"""Repository layer for schema `app` (plain psycopg, dict rows).

Explicit SQL by design (no ORM): 6 tables, full control, zero magic.
All functions open short-lived connections via the application DSN.
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from functools import partial
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import get_settings


def _json_default(o: Any):
    """JSON serializer for database-native types that stdlib json ignores.

    Decimals become floats (preview/display purposes only — the canonical
    values remain in the ERP tables and are re-obtained by re-running the
    SQL); dates/datetimes become ISO-8601 strings.
    """
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    raise TypeError(f"Not JSON serializable: {type(o).__name__}")


_dumps = partial(json.dumps, default=_json_default, ensure_ascii=False)


def _jsonb(obj: Any) -> Json | None:
    return Json(obj, dumps=_dumps) if obj is not None else None


def _conn() -> psycopg.Connection:
    return psycopg.connect(get_settings().app_dsn, row_factory=dict_row)


# ------------------------------------------------------------------- users

_USER_COLS = ("user_id, email, first_name, last_name, job_title, department, "
              "role, (avatar IS NOT NULL) AS has_avatar, created_at")


def count_users() -> int:
    with _conn() as c:
        return c.execute("SELECT count(*) FROM app.users").fetchone()["count"]


def create_user(email: str, password_hash: str, first_name: str, last_name: str,
                job_title: str, department: str, role: str) -> dict:
    with _conn() as c:
        return c.execute(
            "INSERT INTO app.users (email, password_hash, first_name, last_name,"
            " job_title, department, role) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            f"RETURNING {_USER_COLS}",
            (email, password_hash, first_name, last_name, job_title,
             department, role)).fetchone()


def get_user_by_email(email: str) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM app.users WHERE email = %s", (email,)).fetchone()


def get_user(user_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            f"SELECT {_USER_COLS} FROM app.users WHERE user_id = %s",
            (user_id,)).fetchone()


def list_users() -> list[dict]:
    with _conn() as c:
        return c.execute(
            f"SELECT {_USER_COLS} FROM app.users ORDER BY user_id").fetchall()


def update_user(user_id: int, fields: dict) -> dict | None:
    """Update a whitelisted subset of user fields; returns the updated row."""
    allowed = {"first_name", "last_name", "job_title", "department", "role"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_user(user_id)
    sets = ", ".join(f"{k} = %s" for k in updates)
    with _conn() as c:
        return c.execute(
            f"UPDATE app.users SET {sets} WHERE user_id = %s RETURNING {_USER_COLS}",
            (*updates.values(), user_id)).fetchone()


def delete_user(user_id: int) -> bool:
    with _conn() as c:
        return c.execute("DELETE FROM app.users WHERE user_id = %s",
                         (user_id,)).rowcount == 1


def count_admins(excluding: int | None = None) -> int:
    with _conn() as c:
        return c.execute(
            "SELECT count(*) FROM app.users WHERE role = 'admin' "
            "AND (%s::int IS NULL OR user_id <> %s)",
            (excluding, excluding)).fetchone()["count"]


def set_avatar(user_id: int, data: bytes, mime: str) -> None:
    with _conn() as c:
        c.execute("UPDATE app.users SET avatar = %s, avatar_mime = %s "
                  "WHERE user_id = %s", (data, mime, user_id))


def get_avatar(user_id: int) -> dict | None:
    with _conn() as c:
        return c.execute("SELECT avatar, avatar_mime FROM app.users "
                         "WHERE user_id = %s AND avatar IS NOT NULL",
                         (user_id,)).fetchone()


# ----------------------------------------------------------- conversations

def create_conversation(user_id: int, title: str) -> dict:
    with _conn() as c:
        return c.execute(
            "INSERT INTO app.conversations (user_id, title) VALUES (%s, %s) "
            "RETURNING conversation_id, title, created_at, updated_at",
            (user_id, title)).fetchone()


def list_conversations(user_id: int) -> list[dict]:
    with _conn() as c:
        return c.execute(
            "SELECT conversation_id, title, created_at, updated_at "
            "FROM app.conversations WHERE user_id = %s ORDER BY updated_at DESC",
            (user_id,)).fetchall()


def get_conversation(conversation_id: int, user_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT conversation_id, user_id, title FROM app.conversations "
            "WHERE conversation_id = %s AND user_id = %s",
            (conversation_id, user_id)).fetchone()


def touch_conversation(conversation_id: int) -> None:
    with _conn() as c:
        c.execute("UPDATE app.conversations SET updated_at = now() "
                  "WHERE conversation_id = %s", (conversation_id,))


# ---------------------------------------------------------------- messages

def add_message(conversation_id: int, role: str, content: str,
                sql_query: str | None = None,
                chart: dict | None = None,
                result_meta: dict | None = None) -> dict:
    with _conn() as c:
        return c.execute(
            "INSERT INTO app.messages (conversation_id, role, content, sql_query, chart, result_meta) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "RETURNING message_id, conversation_id, role, content, sql_query, chart, result_meta, created_at",
            (conversation_id, role, content, sql_query,
             _jsonb(chart), _jsonb(result_meta))).fetchone()


def list_messages(conversation_id: int) -> list[dict]:
    with _conn() as c:
        return c.execute(
            "SELECT message_id, role, content, sql_query, chart, result_meta, created_at "
            "FROM app.messages WHERE conversation_id = %s ORDER BY message_id",
            (conversation_id,)).fetchall()

# ------------------------------------------------------------- saved charts

def create_saved_chart(user_id: int, title: str, sql_query: str,
                       chart_spec: dict) -> dict:
    with _conn() as c:
        return c.execute(
            "INSERT INTO app.saved_charts (user_id, title, sql_query, chart_spec) "
            "VALUES (%s, %s, %s, %s) "
            "RETURNING chart_id, title, sql_query, chart_spec, created_at, updated_at",
            (user_id, title, sql_query, _jsonb(chart_spec))).fetchone()


def list_saved_charts(user_id: int) -> list[dict]:
    with _conn() as c:
        return c.execute(
            "SELECT chart_id, title, sql_query, chart_spec, created_at, updated_at "
            "FROM app.saved_charts WHERE user_id = %s ORDER BY chart_id",
            (user_id,)).fetchall()


def get_saved_chart(chart_id: int, user_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT chart_id, user_id, title, sql_query, chart_spec "
            "FROM app.saved_charts WHERE chart_id = %s AND user_id = %s",
            (chart_id, user_id)).fetchone()


def get_saved_chart_any(chart_id: int) -> dict | None:
    """Fetch a chart regardless of owner (permission checked by caller)."""
    with _conn() as c:
        return c.execute(
            "SELECT chart_id, user_id, title, sql_query, chart_spec "
            "FROM app.saved_charts WHERE chart_id = %s", (chart_id,)).fetchone()


def delete_saved_chart(chart_id: int, user_id: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM app.saved_charts WHERE chart_id = %s AND user_id = %s",
            (chart_id, user_id))
        return cur.rowcount == 1

def list_all_saved_charts() -> list[dict]:
    """All users' saved charts (reactivity engine index; not exposed via API)."""
    with _conn() as c:
        return c.execute(
            "SELECT chart_id, user_id, title, sql_query, chart_spec "
            "FROM app.saved_charts ORDER BY chart_id").fetchall()


# --------------------------------------------------------------- dashboards

def create_dashboard(owner_id: int, title: str, description: str | None) -> dict:
    with _conn() as c:
        return c.execute(
            "INSERT INTO app.dashboards (owner_id, title, description) "
            "VALUES (%s, %s, %s) RETURNING dashboard_id, owner_id, title, "
            "description, is_shared, created_at, updated_at",
            (owner_id, title, description)).fetchone()


def list_dashboards_for(user_id: int) -> list[dict]:
    """The user's own dashboards plus every shared one, with owner identity."""
    with _conn() as c:
        return c.execute(
            "SELECT d.dashboard_id, d.owner_id, d.title, d.description, "
            "       d.is_shared, d.created_at, d.updated_at, "
            "       u.first_name AS owner_first_name, u.last_name AS owner_last_name, "
            "       (SELECT count(*) FROM app.dashboard_charts dc "
            "        WHERE dc.dashboard_id = d.dashboard_id) AS chart_count "
            "FROM app.dashboards d JOIN app.users u ON u.user_id = d.owner_id "
            "WHERE d.owner_id = %s OR d.is_shared "
            "ORDER BY d.updated_at DESC", (user_id,)).fetchall()


def get_dashboard(dashboard_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT d.*, u.first_name AS owner_first_name, "
            "       u.last_name AS owner_last_name "
            "FROM app.dashboards d JOIN app.users u ON u.user_id = d.owner_id "
            "WHERE d.dashboard_id = %s", (dashboard_id,)).fetchone()


def update_dashboard(dashboard_id: int, fields: dict) -> dict | None:
    allowed = {"title", "description", "is_shared"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_dashboard(dashboard_id)
    sets = ", ".join(f"{k} = %s" for k in updates)
    with _conn() as c:
        c.execute(f"UPDATE app.dashboards SET {sets}, updated_at = now() "
                  "WHERE dashboard_id = %s", (*updates.values(), dashboard_id))
    return get_dashboard(dashboard_id)


def delete_dashboard(dashboard_id: int) -> bool:
    with _conn() as c:
        return c.execute("DELETE FROM app.dashboards WHERE dashboard_id = %s",
                         (dashboard_id,)).rowcount == 1


def dashboard_charts(dashboard_id: int) -> list[dict]:
    with _conn() as c:
        return c.execute(
            "SELECT sc.chart_id, sc.title, sc.sql_query, sc.chart_spec, dc.position "
            "FROM app.dashboard_charts dc "
            "JOIN app.saved_charts sc USING (chart_id) "
            "WHERE dc.dashboard_id = %s ORDER BY dc.position, sc.chart_id",
            (dashboard_id,)).fetchall()


def add_chart_to_dashboard(dashboard_id: int, chart_id: int) -> None:
    with _conn() as c:
        c.execute("INSERT INTO app.dashboard_charts (dashboard_id, chart_id, position) "
                  "VALUES (%s, %s, (SELECT coalesce(max(position)+1, 0) "
                  "  FROM app.dashboard_charts WHERE dashboard_id = %s)) "
                  "ON CONFLICT DO NOTHING", (dashboard_id, chart_id, dashboard_id))
        c.execute("UPDATE app.dashboards SET updated_at = now() "
                  "WHERE dashboard_id = %s", (dashboard_id,))


def remove_chart_from_dashboard(dashboard_id: int, chart_id: int) -> bool:
    with _conn() as c:
        return c.execute(
            "DELETE FROM app.dashboard_charts "
            "WHERE dashboard_id = %s AND chart_id = %s",
            (dashboard_id, chart_id)).rowcount == 1


def shared_chart_ids() -> set[int]:
    """Charts appearing on at least one shared dashboard (live for everyone)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT dc.chart_id FROM app.dashboard_charts dc "
            "JOIN app.dashboards d USING (dashboard_id) WHERE d.is_shared").fetchall()
        return {r["chart_id"] for r in rows}


def chart_is_shared(chart_id: int) -> bool:
    with _conn() as c:
        return c.execute(
            "SELECT EXISTS (SELECT 1 FROM app.dashboard_charts dc "
            "JOIN app.dashboards d USING (dashboard_id) "
            "WHERE d.is_shared AND dc.chart_id = %s)", (chart_id,)
        ).fetchone()["exists"]


# ----------------------------------------------------------------- comments

def add_comment(dashboard_id: int, user_id: int, content: str) -> dict:
    with _conn() as c:
        row = c.execute(
            "INSERT INTO app.dashboard_comments (dashboard_id, user_id, content) "
            "VALUES (%s, %s, %s) RETURNING comment_id, dashboard_id, user_id, "
            "content, created_at", (dashboard_id, user_id, content)).fetchone()
        author = c.execute(
            "SELECT first_name, last_name, job_title, "
            "(avatar IS NOT NULL) AS has_avatar FROM app.users WHERE user_id = %s",
            (user_id,)).fetchone()
    return {**row, **author}


def list_comments(dashboard_id: int) -> list[dict]:
    with _conn() as c:
        return c.execute(
            "SELECT cm.comment_id, cm.dashboard_id, cm.user_id, cm.content, "
            "       cm.created_at, u.first_name, u.last_name, u.job_title, "
            "       (u.avatar IS NOT NULL) AS has_avatar "
            "FROM app.dashboard_comments cm JOIN app.users u USING (user_id) "
            "WHERE cm.dashboard_id = %s ORDER BY cm.comment_id", (dashboard_id,)).fetchall()


def delete_comment(comment_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            "DELETE FROM app.dashboard_comments WHERE comment_id = %s "
            "RETURNING comment_id, dashboard_id, user_id", (comment_id,)).fetchone()


def get_comment(comment_id: int) -> dict | None:
    with _conn() as c:
        return c.execute("SELECT * FROM app.dashboard_comments "
                         "WHERE comment_id = %s", (comment_id,)).fetchone()
