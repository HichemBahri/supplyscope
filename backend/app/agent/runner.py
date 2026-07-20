"""Public entrypoint: ask the agent a question."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.agent.graph import build_graph
from app.agent.state import AgentState, SqlAttempt
from app.config import get_settings
from app.db.introspection import SchemaCache
from app.llm.factory import Tier, get_llm

_schema_cache: SchemaCache | None = None


def _schema_doc() -> str:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = SchemaCache(get_settings().app_dsn)
    return _schema_cache.get()


@dataclass
class AgentAnswer:
    question: str
    answer: str
    sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    duration_ms: float
    attempts: list[SqlAttempt]
    chart: dict
    failed: bool


def ask(question: str, tier: Tier = "fast") -> AgentAnswer:
    graph = build_graph(get_llm(tier))
    state: AgentState = {
        "question": question,
        "schema_doc": _schema_doc(),
        "current_date": dt.date.today().isoformat(),
    }
    out: AgentState = graph.invoke(state)
    return AgentAnswer(
        question=question,
        answer=out.get("answer", ""),
        sql=out.get("sql", ""),
        columns=out.get("columns", []),
        rows=out.get("rows", []),
        row_count=out.get("row_count", 0),
        truncated=out.get("truncated", False),
        duration_ms=out.get("duration_ms", 0.0),
        attempts=out.get("attempts", []),
        chart=out.get("chart", {}),
        failed=bool(out.get("error")),
    )
