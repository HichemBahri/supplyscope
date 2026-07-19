"""Unit + integration tests for the safe SQL executor (defense-in-depth).

Unit tests (no DB): statement validation.
Integration tests (need the seeded Postgres): execution, limits, and the
crucial proof that layer 1 (the agent_reader role) blocks writes even if
layer 2 (the validator) were bypassed.
"""
from __future__ import annotations

import psycopg
import pytest

from app.config import get_settings
from app.db.safe_executor import (
    SQLExecutionError,
    SQLValidationError,
    execute_readonly,
    validate_sql,
)

# ----------------------------------------------------------------- unit tests

@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select po_number, total_amount from erp.purchase_orders limit 5",
    "WITH t AS (SELECT 1 AS x) SELECT * FROM t",
    "SELECT * FROM erp.projects ORDER BY created_at OFFSET 10",  # 'offset'/'created' must not trip keyword scan
    "SELECT 1; ",   # trailing semicolon tolerated
])
def test_validate_accepts_reads(sql):
    assert validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "INSERT INTO erp.clients VALUES (1)",
    "DROP TABLE erp.po_lines",
    "SELECT 1; DELETE FROM erp.payments",       # stacked statements
    "UPDATE erp.assets SET condition='good'",
    "EXPLAIN ANALYZE SELECT 1",                  # not a plain read
    "  -- sneaky\nTRUNCATE erp.boqs",
    "",
])
def test_validate_rejects_non_reads(sql):
    with pytest.raises(SQLValidationError):
        validate_sql(sql)


# ---------------------------------------------------------- integration tests

pytestmark_db = pytest.mark.integration


@pytest.mark.integration
def test_execute_simple_select():
    res = execute_readonly("SELECT project_code, status FROM erp.projects ORDER BY project_code")
    assert res.columns == ["project_code", "status"]
    assert res.row_count > 0 and not res.truncated
    assert res.duration_ms < 5000


@pytest.mark.integration
def test_row_cap_truncates():
    res = execute_readonly("SELECT * FROM erp.po_lines", max_rows=10)
    assert res.row_count == 10 and res.truncated


@pytest.mark.integration
def test_db_error_is_surfaced_for_self_correction():
    with pytest.raises(SQLExecutionError) as e:
        execute_readonly("SELECT nonexistent_column FROM erp.projects")
    assert "nonexistent_column" in str(e.value)


@pytest.mark.integration
def test_layer1_role_blocks_writes_even_without_validator():
    """Bypass the validator entirely: PostgreSQL itself must refuse."""
    s = get_settings()
    with psycopg.connect(s.agent_dsn) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO erp.clients (client_code,name,country,sector) "
                         "VALUES ('HACK','x','x','oil_gas')")
    with psycopg.connect(s.agent_dsn) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM app.users_probe_nonexistent")
