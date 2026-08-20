"""Expert-system alert endpoints."""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from app.api.deps import get_current_user, require_role
from app.api.routes_admin import require_admin
from app.config import get_settings
from app.expert.rules import RULES

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _conn():
    return psycopg.connect(get_settings().app_dsn, row_factory=dict_row,
                           autocommit=True)


@router.get("")
def list_alerts(status: str | None = None, severity: str | None = None,
                user: dict = Depends(get_current_user)) -> list[dict]:
    q = "SELECT * FROM es.alerts"
    clauses, params = [], []
    if status:
        clauses.append("status = %s"); params.append(status)
    else:
        clauses.append("status <> 'resolved'")
    if severity:
        clauses.append("severity = %s"); params.append(severity)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += (" ORDER BY CASE severity WHEN 'critical' THEN 0"
          " WHEN 'warning' THEN 1 ELSE 2 END, last_seen DESC")
    with _conn() as c:
        try:
            return c.execute(q, params).fetchall()
        except psycopg.errors.UndefinedTable:
            return []


@router.get("/summary")
def summary(user: dict = Depends(get_current_user)) -> dict:
    with _conn() as c:
        try:
            rows = c.execute(
                "SELECT severity, count(*) AS n FROM es.alerts "
                "WHERE status <> 'resolved' GROUP BY severity").fetchall()
        except psycopg.errors.UndefinedTable:
            rows = []
    by = {r["severity"]: r["n"] for r in rows}
    return {"critical": by.get("critical", 0), "warning": by.get("warning", 0),
            "info": by.get("info", 0), "total": sum(by.values())}


@router.get("/rules")
def rule_catalog(user: dict = Depends(get_current_user)) -> list[dict]:
    return [{"code": r.code, "name": r.name, "severity": r.severity,
             "description": r.description} for r in RULES]


@router.post("/{alert_id}/ack")
def acknowledge(alert_id: int,
                user: dict = Depends(require_role("admin", "manager"))) -> dict:
    with _conn() as c:
        row = c.execute(
            """
            UPDATE es.alerts
            SET status = 'acknowledged', acknowledged_by = %s,
                acknowledged_at = now()
            WHERE alert_id = %s AND status = 'active'
            RETURNING alert_id, status
            """, (user["user_id"], alert_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Alert not found or not active")
    return row


@router.post("/evaluate")
def evaluate(user: dict = Depends(require_admin)) -> dict:
    from app.expert.engine import evaluate_all
    return evaluate_all()
