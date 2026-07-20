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

def create_user(email: str, password_hash: str, display_name: str) -> dict:
    with _conn() as c:
        return c.execute(
            "INSERT INTO app.users (email, password_hash, display_name) "
            "VALUES (%s, %s, %s) RETURNING user_id, email, display_name, created_at",
            (email, password_hash, display_name)).fetchone()


def get_user_by_email(email: str) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM app.users WHERE email = %s", (email,)).fetchone()


def get_user(user_id: int) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT user_id, email, display_name FROM app.users WHERE user_id = %s",
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


def delete_saved_chart(chart_id: int, user_id: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM app.saved_charts WHERE chart_id = %s AND user_id = %s",
            (chart_id, user_id))
        return cur.rowcount == 1