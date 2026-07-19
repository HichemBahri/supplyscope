"""Graph-logic tests with a scripted fake LLM: deterministic, free, no API.

The fake returns pre-recorded replies in order, letting us assert the graph's
routing: happy path, self-correction path, and give-up path.
"""
from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent.graph import build_graph
from app.agent.nodes import MAX_SQL_ATTEMPTS, extract_sql

BASE_STATE = {
    "question": "How many projects are active?",
    "schema_doc": "### erp.projects\n- status text",
    "current_date": "2026-07-18",
}


def fake_llm(*replies: str) -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(responses=[AIMessage(r) for r in replies])


# ------------------------------------------------------------------ unit

def test_extract_sql_variants():
    assert extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert extract_sql("```\nSELECT 2\n```") == "SELECT 2"
    assert extract_sql("SELECT 3") == "SELECT 3"
    assert extract_sql("Here you go:\n```SQL\nSELECT 4\n```\nEnjoy!") == "SELECT 4"


# ------------------------------------------------------------ integration

@pytest.mark.integration
def test_happy_path_no_correction():
    llm = fake_llm(
        "```sql\nSELECT count(*) AS n FROM erp.projects WHERE status='active'\n```",
        "There are N active projects.",
    )
    out = build_graph(llm).invoke(dict(BASE_STATE))
    assert out["row_count"] == 1 and out["columns"] == ["n"]
    assert out.get("attempts") == [] and "error" not in out
    assert out["answer"] == "There are N active projects."


@pytest.mark.integration
def test_self_correction_path():
    llm = fake_llm(
        "```sql\nSELECT nonexistent_col FROM erp.projects\n```",   # fails
        "```sql\nSELECT count(*) AS n FROM erp.projects\n```",     # fix works
        "Answer after one correction.",
    )
    out = build_graph(llm).invoke(dict(BASE_STATE))
    assert len(out["attempts"]) == 1
    assert "nonexistent_col" in out["attempts"][0]["error"]
    assert out["row_count"] == 1
    assert out["answer"] == "Answer after one correction."


@pytest.mark.integration
def test_gives_up_after_max_attempts():
    bad = "```sql\nSELECT nope FROM erp.projects\n```"
    llm = fake_llm(*([bad] * MAX_SQL_ATTEMPTS))
    out = build_graph(llm).invoke(dict(BASE_STATE))
    assert len(out["attempts"]) == MAX_SQL_ATTEMPTS
    assert out.get("error")
    assert "could not produce a working query" in out["answer"]


@pytest.mark.integration
def test_write_attempt_is_blocked_and_corrected():
    llm = fake_llm(
        "```sql\nDELETE FROM erp.projects\n```",                  # validator blocks
        "```sql\nSELECT count(*) AS n FROM erp.projects\n```",
        "Blocked then answered.",
    )
    out = build_graph(llm).invoke(dict(BASE_STATE))
    assert "Only SELECT/WITH" in out["attempts"][0]["error"]
    assert out["answer"] == "Blocked then answered."
