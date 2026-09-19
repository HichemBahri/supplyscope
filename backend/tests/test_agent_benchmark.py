"""Phase 15 — agent benchmark harness.

These tests never call a real LLM. They prove (1) every ground truth is
sound, (2) the grader's leniencies and strictnesses behave as documented,
(3) the runner scores a perfect oracle at exactly 100% and attributes
rescues/failures correctly, (4) results are cached so a re-run costs
nothing, and (5) the harness plugs into the real LangGraph agent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.config import get_settings
from app.eval.grader import grade
from app.eval.questions import BY_ID, QUESTIONS, TIERS
from scripts.bench_agent import run, summarize


# ------------------------------------------------------------ ground truth

def test_every_truth_query_is_sound():
    with psycopg.connect(get_settings().app_dsn) as c:
        for q in QUESTIONS:
            rows = c.execute(q.truth_sql).fetchall()
            assert rows, f"{q.qid}: empty truth"
            if q.kind in ("count", "scalar"):
                assert len(rows) == 1 and rows[0][0] not in (None, 0), f"{q.qid} degenerate"
            if q.kind == "ordered":
                assert len(rows) >= 2
            assert q.tier in TIERS


def test_bank_shape():
    assert len(QUESTIONS) >= 40
    assert len({q.qid for q in QUESTIONS}) == len(QUESTIONS)
    for t in TIERS:
        assert sum(q.tier == t for q in QUESTIONS) >= 10
    # the injected stories are covered
    assert {"M01", "M05", "M07", "H01"} <= set(BY_ID)


# ------------------------------------------------------------------ grader

def test_grader_count_exact_and_scalar_tolerance():
    assert grade("count", [[361]], [[Decimal("361")]]).correct
    assert not grade("count", [[361]], [[360]]).correct
    assert grade("scalar", [[Decimal("77.0")]], [[77.9]]).correct          # within 2%
    assert not grade("scalar", [[Decimal("77.0")]], [[80.0]]).correct
    assert grade("scalar", [[Decimal("77.0")]], [[0.771]]).correct         # ratio ≡ percent
    assert grade("scalar", [[Decimal("1.495")]], [["1.50"]], 0.05).correct  # text number


def test_grader_entities_aliases_and_ordering():
    truth = [["Trans-Sahara Steel Trading", "SUP-TSS", Decimal("0.167")]]
    assert grade("top1", truth, [["SUP-TSS", 0.17]]).correct               # code alias
    assert grade("top1", truth, [["trans-sahara steel trading", 5]]).correct
    v = grade("top1", truth, [["Lyon Systèmes", 0.94], ["Trans-Sahara Steel Trading", 0.17]])
    assert not v.correct and "ordering" in v.reason
    assert not grade("top1", truth, [["Nobody", 1]]).correct
    assert grade("top1", [[2025, Decimal("0.714")]], [["2025", 71.4]]).correct   # numeric entity


def test_grader_ordered_and_set():
    t = [["A Corp", "SUP-A"], ["B Corp", "SUP-B"], ["C Corp", "SUP-C"]]
    assert grade("ordered", t, [["A Corp"], ["B Corp"], ["C Corp"], ["D"]]).correct
    assert not grade("ordered", t, [["B Corp"], ["A Corp"], ["C Corp"]]).correct
    assert grade("set", t[:2], [["SUP-B", 1], ["A Corp", 2]]).correct
    assert not grade("set", t[:2], [["A Corp"]]).correct                    # missing one
    assert not grade("set", t[:2], [["A Corp"], ["B Corp"], ["C Corp"]]).correct  # extra
    assert not grade("top1", t, []).correct


# ------------------------------------------------------------------ runner

@dataclass
class FakeAnswer:
    question: str
    sql: str
    columns: list
    rows: list
    row_count: int
    failed: bool = False
    attempts: list = field(default_factory=list)
    answer: str = "ok"
    duration_ms: float = 1.0
    chart: dict = field(default_factory=dict)
    truncated: bool = False


def _oracle(question: str, tier: str) -> FakeAnswer:
    """An agent that always runs the ground-truth SQL: must score 100%."""
    q = next(q for q in QUESTIONS if q.question == question)
    with psycopg.connect(get_settings().app_dsn) as c:
        cur = c.execute(q.truth_sql)
        rows = [list(r) for r in cur.fetchall()]
        cols = [d.name for d in cur.description]
    return FakeAnswer(question, q.truth_sql, cols, rows, len(rows))


def test_oracle_scores_100(tmp_path):
    s = run("fast", out=tmp_path, ask_fn=_oracle, chart=False)
    assert s["overall"]["accuracy"] == 100.0
    assert s["overall"]["rescued"] == 0 and s["overall"]["failed"] == 0
    assert (tmp_path / "agent_bench_fast.csv").exists()
    assert (tmp_path / "agent_bench_fast.md").exists()


def test_rescue_and_failure_attribution(tmp_path):
    def mixed(question, tier):
        a = _oracle(question, tier)
        if a.question == BY_ID["E01"].question:          # rescued on 2nd try
            a.attempts = [{"sql": "SELECT nope", "error": "relation nope"}]
        if a.question == BY_ID["E02"].question:          # gave up after 3
            a.failed, a.rows, a.row_count = True, [], 0
            a.attempts = [{"sql": "x", "error": "e"}] * 3
        if a.question == BY_ID["E03"].question:          # confidently wrong
            a.rows = [[999]]
        return a

    s = run("fast", only={"E01", "E02", "E03", "E04"}, out=tmp_path, ask_fn=mixed,
            chart=True)
    assert s["overall"] == {"n": 4, "correct": 2, "accuracy": 50.0, "first_try": 1,
                            "rescued": 1, "wrong": 1, "failed": 1}
    sc = s["self_correction"]
    assert sc == {"needed_correction": 2, "rescued": 1, "rescue_rate": 50.0}
    assert (tmp_path / "agent_bench_fast.png").stat().st_size > 5000


def test_cache_makes_rerun_free(tmp_path):
    calls = {"n": 0}

    def counting(question, tier):
        calls["n"] += 1
        return _oracle(question, tier)

    run("fast", only={"E01", "E02"}, out=tmp_path, ask_fn=counting, chart=False)
    assert calls["n"] == 2

    def must_not_run(question, tier):
        raise AssertionError("cache miss — the LLM would have been billed")

    s = run("fast", only={"E01", "E02"}, out=tmp_path, ask_fn=must_not_run, chart=False)
    assert s["overall"]["n"] == 2 and s["overall"]["accuracy"] == 100.0
    cached = json.loads((tmp_path / "agent_bench_fast.json").read_text())
    assert {r["qid"] for r in cached} == {"E01", "E02"}


def test_harness_plugs_into_real_graph(tmp_path):
    """The real LangGraph agent with a fake LLM: proves the runner consumes
    genuine AgentAnswer objects, including their attempts list."""
    from app.agent.graph import build_graph
    from app.agent.runner import AgentAnswer, _schema_doc
    import datetime as dt

    def ask_with_fake_llm(question, tier):
        q = BY_ID["E05"]
        llm = FakeMessagesListChatModel(responses=[
            AIMessage("```sql\nSELECT count(*) FROM erp.shipmentz\n```"),   # typo → error
            AIMessage(f"```sql\n{q.truth_sql}\n```"),                        # the fix
            AIMessage('```json\n{"chart_type": "kpi", "title": "Held", "value_field": "count"}\n```'),
            AIMessage("Two shipments are on customs hold."),
        ])
        out = build_graph(llm).invoke({"question": question, "schema_doc": _schema_doc(),
                                       "current_date": dt.date.today().isoformat()})
        return AgentAnswer(question=question, answer=out.get("answer", ""),
                           sql=out.get("sql", ""), columns=out.get("columns", []),
                           rows=out.get("rows", []), row_count=out.get("row_count", 0),
                           truncated=out.get("truncated", False),
                           duration_ms=out.get("duration_ms", 0.0),
                           attempts=out.get("attempts", []), chart=out.get("chart", {}),
                           failed=bool(out.get("error")))

    s = run("fast", only={"E05"}, out=tmp_path, ask_fn=ask_with_fake_llm, chart=False)
    assert s["overall"]["correct"] == 1
    assert s["overall"]["rescued"] == 1          # the typo was self-corrected
    assert s["self_correction"]["rescue_rate"] == 100.0
