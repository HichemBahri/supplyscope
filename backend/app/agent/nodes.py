"""Agent graph nodes.

Each node is a pure-ish function AgentState -> partial AgentState update.
The LLM is injected (build_nodes) so tests can substitute a scripted fake.
"""
from __future__ import annotations

import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent import prompts
from app.agent.charts import ChartSpecError, parse_chart_spec
from app.agent.state import AgentState
from app.db.safe_executor import (
    SQLExecutionError,
    SQLValidationError,
    execute_readonly,
)

MAX_SQL_ATTEMPTS = 3
_SQL_FENCE = re.compile(r"```sql\s*(.+?)```", re.DOTALL | re.IGNORECASE)
_JSON_FENCE = re.compile(r"```json\s*(.+?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE = re.compile(r"```\s*(.+?)```", re.DOTALL)


def extract_sql(text: str) -> str:
    """Pull the SQL out of a fenced block; tolerate fence-less replies."""
    if m := _SQL_FENCE.search(text):
        return m.group(1).strip()
    if m := _ANY_FENCE.search(text):
        return m.group(1).strip()
    return text.strip()


def _result_table(state: AgentState, max_rows: int = 30, max_cell: int = 60) -> str:
    cols = state.get("columns", [])
    rows = state.get("rows", [])[:max_rows]
    if not cols:
        return "(no columns)"
    def cell(v) -> str:
        s = "NULL" if v is None else str(v)
        return s if len(s) <= max_cell else s[: max_cell - 1] + "…"
    lines = [" | ".join(cols)]
    lines += [" | ".join(cell(v) for v in r) for r in rows]
    if len(state.get("rows", [])) > max_rows:
        lines.append(f"... ({len(state['rows']) - max_rows} more rows omitted)")
    return "\n".join(lines)


def build_nodes(llm: BaseChatModel):
    """Return the node functions bound to a concrete chat model."""

    def _sql_system(state: AgentState) -> SystemMessage:
        return SystemMessage(prompts.SQL_SYSTEM.format(
            current_date=state["current_date"], schema_doc=state["schema_doc"]))

    def generate_sql(state: AgentState) -> AgentState:
        reply = llm.invoke([
            _sql_system(state),
            HumanMessage(prompts.SQL_GENERATE_USER.format(question=state["question"])),
        ])
        return {"sql": extract_sql(reply.content), "attempts": []}

    def execute_sql(state: AgentState) -> AgentState:
        try:
            res = execute_readonly(state["sql"])
        except (SQLValidationError, SQLExecutionError) as exc:
            attempts = list(state.get("attempts", []))
            attempts.append({"sql": state["sql"], "error": str(exc)})
            update: AgentState = {"attempts": attempts}
            if len(attempts) >= MAX_SQL_ATTEMPTS:
                update["error"] = str(exc)
            return update
        return {
            "columns": res.columns,
            "rows": [list(r) for r in res.rows],
            "row_count": res.row_count,
            "truncated": res.truncated,
            "duration_ms": res.duration_ms,
            "sql": res.sql,
        }

    def fix_sql(state: AgentState) -> AgentState:
        last = state["attempts"][-1]
        reply = llm.invoke([
            _sql_system(state),
            HumanMessage(prompts.SQL_FIX_USER.format(
                question=state["question"],
                failed_sql=last["sql"],
                db_error=last["error"])),
        ])
        return {"sql": extract_sql(reply.content)}

    def decide_chart(state: AgentState) -> AgentState:
        """Pick a chart spec for the result; one repair retry; table fallback."""
        if not state.get("row_count"):
            return {"chart": {"chart_type": "table", "title": "Résultat"}}
        user = HumanMessage(prompts.CHART_USER.format(
            question=state["question"],
            columns=state["columns"],
            sample_rows=_result_table(state, max_rows=5)))
        messages = [SystemMessage(prompts.CHART_SYSTEM), user]
        for attempt in range(2):
            reply = llm.invoke(messages)
            raw = reply.content
            if m := (_JSON_FENCE.search(raw) or _ANY_FENCE.search(raw)):
                raw = m.group(1)
            try:
                spec = parse_chart_spec(raw.strip(), state["columns"])
                return {"chart": spec.model_dump()}
            except (ChartSpecError, json.JSONDecodeError) as exc:
                messages = [SystemMessage(prompts.CHART_SYSTEM), user,
                            reply,
                            HumanMessage(prompts.CHART_FIX_USER.format(error=str(exc)))]
        # both attempts invalid: universal fallback
        return {"chart": {"chart_type": "table",
                          "title": state["question"][:80]}}

    def synthesize_answer(state: AgentState) -> AgentState:
        if state.get("error"):
            return {"answer": prompts.FAILURE_ANSWER.format(
                n=len(state.get("attempts", [])), error=state["error"])}
        truncated_note = ", TRUNCATED to first rows" if state.get("truncated") else ""
        reply = llm.invoke([
            SystemMessage(prompts.ANSWER_SYSTEM),
            HumanMessage(prompts.ANSWER_USER.format(
                question=state["question"],
                sql=state["sql"],
                row_count=state.get("row_count", 0),
                truncated_note=truncated_note,
                result_table=_result_table(state))),
        ])
        return {"answer": reply.content.strip()}

    return generate_sql, execute_sql, fix_sql, decide_chart, synthesize_answer
