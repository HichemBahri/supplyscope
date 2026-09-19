"""Phase 13a — agentic dashboard synthesis: plan parsing, fan-out through
the agent, assembly, partial-failure tolerance."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from app.agent.dashboard_synth import plan_dashboard, synthesize_dashboard
from app.db import app_repo


class FakePlanner:
    def __init__(self, payload):
        self.payload = payload

    def invoke(self, _prompt):
        @dataclass
        class R: content: str
        return R(content=self.payload)


PLAN = json.dumps({
    "title": "Supplier performance",
    "description": "Overview of supplier delivery and cost",
    "views": [
        {"question": "How many active suppliers do we have?", "kind": "kpi"},
        {"question": "Top suppliers by on-time rate", "kind": "ranking"},
        {"question": "THIS ONE WILL FAIL", "kind": "trend"},
    ],
})


from dataclasses import field


@dataclass
class FakeAnswer:
    failed: bool
    chart: dict
    sql: str
    answer: str = ""
    row_count: int = 1
    columns: list = field(default_factory=lambda: ["name", "rate"])
    rows: list = field(default_factory=lambda: [["a", 1], ["b", 2]])


def fake_ask(question: str, tier: str) -> FakeAnswer:
    if "FAIL" in question:
        return FakeAnswer(True, {}, "", "could not answer")
    return FakeAnswer(False,
                      {"chart_type": "kpi", "title": question[:40],
                       "value_field": "n"},
                      "SELECT count(*) AS n FROM erp.suppliers")


def _user():
    return app_repo.create_user(
        f"synth-{uuid.uuid4().hex[:8]}@example.com", "x", "Syn", "Th",
        "Analyst", "IT", "analyst")["user_id"]


def test_plan_parses_even_with_prose_wrapping():
    plan = plan_dashboard("suppliers",
                          FakePlanner("Here you go:\n" + PLAN + "\nEnjoy!"))
    assert plan["title"] == "Supplier performance"
    assert len(plan["views"]) == 3


def test_constant_metric_view_is_dropped():
    """The zero-variance gate: an all-identical metric (e.g. every supplier
    at 100%) ships no chart."""
    uid = _user()

    def ask_const(question, tier):
        a = fake_ask(question, tier)
        if not a.failed:
            a.rows = [["s1", 100.0], ["s2", 100.0], ["s3", 100.0],
                      ["s4", 100.0]]
            a.chart = {"chart_type": "bar", "title": "t",
                       "x_field": "name", "y_fields": ["rate"]}
        return a

    out = synthesize_dashboard("acceptance", uid,
                               llm=FakePlanner(PLAN), ask_fn=ask_const)
    assert len(out["created"]) == 0
    assert all("constant" in f["reason"] for f in out["failed"][:2])
    app_repo.delete_dashboard(out["dashboard_id"])


def test_synthesis_assembles_and_tolerates_partial_failure():
    uid = _user()
    out = synthesize_dashboard("supplier performance", uid,
                               llm=FakePlanner(PLAN), ask_fn=fake_ask)
    assert out["planned"] == 3
    assert len(out["created"]) == 2 and len(out["failed"]) == 1
    assert out["failed"][0]["question"] == "THIS ONE WILL FAIL"
    # the dashboard really exists and carries exactly the surviving charts
    charts = app_repo.dashboard_charts(out["dashboard_id"])
    assert len(charts) == 2
    # cleanup
    app_repo.delete_dashboard(out["dashboard_id"])


def test_saved_synth_charts_are_reactive_like_any_other():
    """A synthesized chart lands in the dependency index — reactivity is
    inherited, not reimplemented."""
    from app.reactivity.deps_index import ChartIndex
    uid = _user()
    out = synthesize_dashboard("suppliers", uid,
                               llm=FakePlanner(PLAN), ask_fn=fake_ask)
    idx = ChartIndex()
    idx.rebuild()
    hit = idx.charts_for({"suppliers"})
    ours = {c["chart_id"] for c in out["created"]} if out["created"] else set()
    assert ours & {c["chart_id"] for c in hit}
    app_repo.delete_dashboard(out["dashboard_id"])


def test_zero_rate_views_are_dropped():
    """0%% on every row of a 'rate' is integer-division or an empty window
    — the gate refuses to ship it (chart-1 class from the field)."""
    uid = _user()

    def ask_zero(question, tier):
        a = fake_ask(question, tier)
        if not a.failed:
            a.columns = ["quarter", "otd_rate_pct"]
            a.rows = [["2026-Q1", 0], ["2026-Q2", None], ["2026-Q3", "0"]]
            a.chart = {"chart_type": "kpi", "title": "On-time rate",
                       "value_field": "otd_rate_pct"}
        return a

    out = synthesize_dashboard("otd rate", uid,
                               llm=FakePlanner(PLAN), ask_fn=ask_zero)
    assert len(out["created"]) == 0
    assert all("zero-valued rate" in f["reason"] for f in out["failed"][:2])
    app_repo.delete_dashboard(out["dashboard_id"])


def test_multi_entity_line_gets_color_field_auto_repaired():
    """The spec grammar now offers color_field on lines, but chart validity
    must not DEPEND on the model obeying prose: synthesis sets the entity
    column deterministically when the model forgets (chart-5 class)."""
    import psycopg

    from app.config import get_settings
    uid = _user()

    def ask_line(question, tier):
        a = fake_ask(question, tier)
        if not a.failed:
            a.columns = ["quarter", "tier", "cycle_days"]
            a.rows = [["2025-Q1", "gold", 30], ["2025-Q1", "silver", 45],
                      ["2025-Q2", "gold", 28], ["2025-Q2", "silver", 41]]
            a.chart = {"chart_type": "line", "title": "Cycle by tier",
                       "x_field": "quarter", "y_fields": ["cycle_days"]}
        return a

    out = synthesize_dashboard("cycle", uid,
                               llm=FakePlanner(PLAN), ask_fn=ask_line)
    assert out["created"], "line views should ship"
    cid = out["created"][0]["chart_id"]
    with psycopg.connect(get_settings().app_dsn) as c:
        spec = c.execute("SELECT chart_spec FROM app.saved_charts "
                         "WHERE chart_id=%s", (cid,)).fetchone()[0]
    assert spec["color_field"] == "tier"
    app_repo.delete_dashboard(out["dashboard_id"])


def test_mixed_scale_series_is_dropped_from_bar():
    """A 0-100%% series beside a 0-60M series is an invisible sliver; the
    repair keeps only series that can share the axis (field evidence)."""
    import psycopg

    from app.config import get_settings
    uid = _user()

    def ask_mixed(question, tier):
        a = fake_ask(question, tier)
        if not a.failed:
            a.columns = ["category", "spend_tnd", "pct_of_total"]
            a.rows = [["steel", 52_000_000, 18.0], ["safety", 46_000_000, 16.0],
                      ["piping", 14_000_000, 5.0]]
            a.chart = {"chart_type": "bar", "title": "Spend", "x_field": "category",
                       "y_fields": ["spend_tnd", "pct_of_total"]}
        return a

    out = synthesize_dashboard("spend", uid, llm=FakePlanner(PLAN), ask_fn=ask_mixed)
    cid = out["created"][0]["chart_id"]
    with psycopg.connect(get_settings().app_dsn) as c:
        spec = c.execute("SELECT chart_spec FROM app.saved_charts WHERE chart_id=%s",
                         (cid,)).fetchone()[0]
    assert spec["y_fields"] == ["spend_tnd"]
    app_repo.delete_dashboard(out["dashboard_id"])


def _spec_of(chart_id):
    import psycopg

    from app.config import get_settings
    with psycopg.connect(get_settings().app_dsn) as c:
        return c.execute("SELECT chart_spec FROM app.saved_charts "
                         "WHERE chart_id=%s", (chart_id,)).fetchone()[0]


MONEY_PLAN = json.dumps({
    "title": "Cost control", "description": "money views",
    "views": [
        {"question": "Payment liability exposure by project in TND",
         "kind": "ranking"},
        {"question": "Delivered-but-unpaid amount by project", "kind": "ranking"},
        {"question": "THIS ONE WILL FAIL", "kind": "trend"},
    ],
})


def test_money_metric_with_tiny_values_is_dropped():
    """'Payment liability exposure' at 0.01–0.03 is not money (field case)."""
    uid = _user()

    def ask(question, tier):
        a = fake_ask(question, tier)
        if not a.failed:
            a.columns = ["project", "exposure_tnd"]
            a.rows = [["p1", 0.01], ["p2", 0.01], ["p3", 0.03]]
            a.chart = {"chart_type": "bar", "title": "Payment liability exposure",
                       "x_field": "project", "y_fields": ["exposure_tnd"]}
        return a
    out = synthesize_dashboard("exposure", uid, llm=FakePlanner(MONEY_PLAN),
                               ask_fn=ask)
    assert not out["created"]
    assert all("monetary" in f["reason"] for f in out["failed"][:2])
    app_repo.delete_dashboard(out["dashboard_id"])


def test_near_constant_ranking_is_dropped():
    uid = _user()

    def ask(question, tier):
        a = fake_ask(question, tier)
        if not a.failed:
            a.columns = ["project", "n_unpaid"]
            a.rows = [[f"p{i}", 1] for i in range(11)] + [["p99", 2]]
            a.chart = {"chart_type": "bar", "title": "Unpaid count by project",
                       "x_field": "project", "y_fields": ["n_unpaid"]}
        return a
    out = synthesize_dashboard("unpaid", uid, llm=FakePlanner(PLAN), ask_fn=ask)
    assert not out["created"]
    assert all("distinct values" in f["reason"] for f in out["failed"][:2])
    app_repo.delete_dashboard(out["dashboard_id"])


def test_pie_with_many_slices_becomes_horizontal_bar():
    uid = _user()

    def ask(question, tier):
        a = fake_ask(question, tier)
        if not a.failed:
            a.columns = ["category", "spend_tnd"]
            a.rows = [[f"cat{i}", 1_000_000 * (i + 1)] for i in range(9)]
            a.chart = {"chart_type": "pie", "title": "Spend share",
                       "label_field": "category", "value_field": "spend_tnd"}
        return a
    out = synthesize_dashboard("spend", uid, llm=FakePlanner(PLAN), ask_fn=ask)
    assert out["created"]
    spec = _spec_of(out["created"][0]["chart_id"])
    assert spec["chart_type"] == "bar" and spec["orientation"] == "h"
    assert spec["x_field"] == "category" and spec["y_fields"] == ["spend_tnd"]
    app_repo.delete_dashboard(out["dashboard_id"])
