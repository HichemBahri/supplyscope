"""Safe execution of LLM-generated SQL — defense-in-depth layer 2.

Layer 1 (the decisive one) is PostgreSQL itself: queries run as the
`agent_reader` role, which has SELECT-only rights on schema `erp` and no
access to schema `app` (db/init/01-schemas.sql). Layer 2, this module,
rejects obviously non-read statements before they reach the database, and
constrains execution with a read-only transaction, a statement timeout and
a row cap. LLM output is treated as untrusted input, always.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import psycopg

from app.config import get_settings


class SQLValidationError(Exception):
    """The statement was rejected before execution."""


class SQLExecutionError(Exception):
    """PostgreSQL rejected the statement; message is safe to feed back to the
    LLM for self-correction."""


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"copy|call|do|vacuum|reindex|cluster|listen|notify|set|reset|"
    r"prepare|execute|deallocate|lock|comment|security|refresh)\b",
    re.IGNORECASE,
)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql.strip()


def validate_sql(sql: str) -> str:
    """Return a cleaned statement or raise SQLValidationError."""
    cleaned = _strip_comments(sql).rstrip(";").strip()
    if not cleaned:
        raise SQLValidationError("Empty SQL statement.")
    if ";" in cleaned:
        raise SQLValidationError("Multiple statements are not allowed.")
    head = cleaned.split(None, 1)[0].lower()
    if head not in ("select", "with"):
        raise SQLValidationError("Only SELECT/WITH read queries are allowed.")
    if m := _FORBIDDEN.search(cleaned):
        raise SQLValidationError(
            f"Forbidden keyword for a read-only query: {m.group(0)!r}.")
    return cleaned


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    row_count: int
    truncated: bool
    duration_ms: float
    sql: str = field(repr=False, default="")

    def to_records(self) -> list[dict]:
        return [dict(zip(self.columns, r)) for r in self.rows]


def execute_readonly(sql: str,
                     max_rows: int | None = None,
                     timeout_ms: int | None = None) -> QueryResult:
    """Validate then execute a read-only query as agent_reader."""
    s = get_settings()
    max_rows = max_rows or s.agent_max_rows
    timeout_ms = timeout_ms or s.agent_sql_timeout_ms
    cleaned = validate_sql(sql)
    t0 = time.perf_counter()
    try:
        with psycopg.connect(s.agent_dsn) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                cur.execute(cleaned)  # type: ignore[arg-type]
                columns = [d.name for d in cur.description or []]
                rows = cur.fetchmany(max_rows + 1)
    except psycopg.errors.QueryCanceled as exc:
        raise SQLExecutionError(
            f"Query exceeded the {timeout_ms} ms time limit.") from exc
    except psycopg.Error as exc:
        msg = (exc.diag.message_primary or str(exc)) if hasattr(exc, "diag") else str(exc)
        detail = getattr(getattr(exc, "diag", None), "message_detail", None)
        raise SQLExecutionError(msg + (f" ({detail})" if detail else "")) from exc
    duration = (time.perf_counter() - t0) * 1000
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return QueryResult(columns=columns, rows=rows, row_count=len(rows),
                       truncated=truncated, duration_ms=round(duration, 1),
                       sql=cleaned)
