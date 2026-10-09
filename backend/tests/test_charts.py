"""Chart spec validation + graph integration of the chart node."""
from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent.charts import ChartSpecError, parse_chart_spec
from app.agent.graph import build_graph

COLS = ["supplier", "otd_rate"]


def test_valid_bar_spec():
    spec = parse_chart_spec(
        '{"chart_type":"bar","title":"OTD par fournisseur",'
        '"x_field":"supplier","y_fields":["otd_rate"],"orientation":"h","stacked":false}',
        COLS)
    assert spec.chart_type == "bar" and spec.orientation == "h"


def test_unknown_column_rejected():
    with pytest.raises(ChartSpecError, match="non-existent result columns"):
        parse_chart_spec(
            '{"chart_type":"kpi","title":"Total spend","value_field":"nope"}', COLS)


def test_unknown_chart_type_rejected():
    with pytest.raises(ChartSpecError):
        parse_chart_spec('{"chart_type":"hologram","title":"X"}', COLS)


BASE_STATE = {
    "question": "How many projects per status?",
    "schema_doc": "### erp.projects\n- status text",
    "current_date": "2026-07-19",
}


def fake(*replies: str) -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(responses=[AIMessage(r) for r in replies])


@pytest.mark.integration
def test_graph_produces_validated_chart():
    llm = fake(
        "```sql\nSELECT status, count(*) AS n FROM erp.projects GROUP BY status\n```",
        '```json\n{"chart_type":"bar","title":"Projets par statut",'
        '"x_field":"status","y_fields":["n"],"orientation":"v","stacked":false}\n```',
        "Réponse.",
    )
    out = build_graph(llm).invoke(dict(BASE_STATE))
    assert out["chart"]["chart_type"] == "bar"
    assert out["chart"]["x_field"] == "status"


@pytest.mark.integration
def test_bad_chart_is_repaired_once():
    llm = fake(
        "```sql\nSELECT status, count(*) AS n FROM erp.projects GROUP BY status\n```",
        '```json\n{"chart_type":"bar","title":"Projets","x_field":"statuss","y_fields":["n"]}\n```',
        '```json\n{"chart_type":"bar","title":"Projets","x_field":"status","y_fields":["n"]}\n```',
        "Réponse.",
    )
    out = build_graph(llm).invoke(dict(BASE_STATE))
    assert out["chart"]["x_field"] == "status"


@pytest.mark.integration
def test_hopeless_chart_falls_back_to_table():
    llm = fake(
        "```sql\nSELECT status, count(*) AS n FROM erp.projects GROUP BY status\n```",
        "not json at all",
        "still not json",
        "Réponse.",
    )
    out = build_graph(llm).invoke(dict(BASE_STATE))
    assert out["chart"]["chart_type"] == "table"


def test_swapped_bar_axes_are_repaired():
    """Field case: the smart tier put the numeric delay in x_field and the
    supplier name in y_fields for a horizontal bar, which rendered as thin
    lines. The repair swaps them; a correct spec is left untouched."""
    from decimal import Decimal
    from app.agent.charts import repair_axes
    cols = ["supplier_name", "avg_delay_days", "n"]
    rows = [["Trans-Sahara", Decimal("20.44"), 18], ["Valencia", Decimal("11.0"), 11]]
    bad = {"chart_type": "bar", "title": "Delay by supplier", "orientation": "h",
           "x_field": "avg_delay_days", "y_fields": ["supplier_name"], "stacked": False}
    fixed = repair_axes(bad, cols, rows)
    assert fixed["x_field"] == "supplier_name" and fixed["y_fields"] == ["avg_delay_days"]
    good = {"chart_type": "bar", "title": "Delay by supplier", "orientation": "h",
            "x_field": "supplier_name", "y_fields": ["avg_delay_days"], "stacked": False}
    assert repair_axes(good, cols, rows) == good
    assert repair_axes(fixed, cols, rows)["x_field"] == "supplier_name"   # idempotent
