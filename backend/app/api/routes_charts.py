"""Saved charts: pin, list, refresh, delete.

A saved chart = (sql_query, chart_spec), the reactive unit of the system:
Phase 4 re-executes sql_query when underlying data changes and pushes fresh
rows to subscribed clients. Saving therefore validates BOTH: the SQL runs
under the same read-only agent_reader pipeline as agent queries (user input
is as untrusted as LLM output), and the spec's fields must exist in the
actual result columns — every stored chart is executable and coherent.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.agent.charts import ChartSpecError, parse_chart_spec
from app.api.deps import get_current_user
from app.api.schemas import ChartDataOut, SaveChartRequest, SavedChartOut
from app.db import app_repo
from app.db.safe_executor import (
    SQLExecutionError,
    SQLValidationError,
    execute_readonly,
)

router = APIRouter(prefix="/api/charts", tags=["charts"])

_PREVIEW_ROWS = 200


def _run(sql: str):
    try:
        return execute_readonly(sql, max_rows=_PREVIEW_ROWS)
    except (SQLValidationError, SQLExecutionError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Chart SQL rejected: {exc}")


@router.post("", response_model=SavedChartOut, status_code=201)
def save_chart(body: SaveChartRequest, request: Request,
               user: dict = Depends(get_current_user)) -> SavedChartOut:
    result = _run(body.sql_query)          # 1) SQL must execute (read-only)
    try:                                   # 2) spec must match its columns
        spec = parse_chart_spec(body.chart_spec, result.columns)
    except ChartSpecError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    saved = app_repo.create_saved_chart(
        user["user_id"], body.title, result.sql, spec.model_dump())
    if (engine := getattr(request.app.state, "reactivity", None)):
        engine.reindex_soon()
    return SavedChartOut(**saved)


@router.get("", response_model=list[SavedChartOut])
def list_charts(user: dict = Depends(get_current_user)) -> list[SavedChartOut]:
    return [SavedChartOut(**c) for c in app_repo.list_saved_charts(user["user_id"])]


@router.get("/{chart_id}/data", response_model=ChartDataOut)
def chart_data(chart_id: int,
               user: dict = Depends(get_current_user)) -> ChartDataOut:
    """Re-execute the chart's SQL and return fresh rows (manual refresh —
    the primitive the Phase-4 reactivity engine automates)."""
    chart = app_repo.get_saved_chart(chart_id, user["user_id"])
    if chart is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chart not found")
    result = _run(chart["sql_query"])
    return ChartDataOut(
        chart_id=chart_id, chart_spec=chart["chart_spec"],
        columns=result.columns,
        rows=[list(r) for r in result.rows],
        row_count=result.row_count, truncated=result.truncated,
        duration_ms=result.duration_ms)


@router.delete("/{chart_id}", status_code=204)
def delete_chart(chart_id: int, request: Request,
                 user: dict = Depends(get_current_user)) -> None:
    if not app_repo.delete_saved_chart(chart_id, user["user_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chart not found")
    if (engine := getattr(request.app.state, "reactivity", None)):
        engine.reindex_soon()
