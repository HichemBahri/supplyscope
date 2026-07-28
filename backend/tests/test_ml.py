"""Phase 7.1 — ML pipeline: features, training, scoring, permissions,
agent access through the ml schema, and reactivity of predictions."""
from __future__ import annotations

import asyncio
import uuid

import psycopg
import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

from app.config import get_settings
from app.db import app_repo
from app.ml import features as F
from app.ml.registry import active_model
from app.ml.scoring import score_open_orders
from app.ml.train_risk import train
from tests.test_agent_graph import BASE_STATE
from tests.test_reactivity import _next_update_for


def test_feature_frames_are_sane():
    df = F.training_frame()
    assert len(df) > 300
    assert df[F.LABEL].dtype == bool
    for col in F.CATEGORICAL + F.NUMERIC + F.BOOLEAN:
        assert col in df.columns, col
        assert not df[col].isna().any(), f"NaN in {col}"
    assert df["supplier_prior_late_rate"].between(-1, 1).all()


def test_training_registers_active_model_and_beats_chance():
    entry = train(verbose=False)
    assert entry["is_active"]
    assert entry["metrics"]["roc_auc"] > 0.6      # frozen world: LogReg ~0.69
    assert set(entry["comparison"]) == {"logistic_regression",
                                        "random_forest", "mlp"}
    assert active_model("delivery_risk")["version"] == entry["version"]


def test_scoring_populates_predictions_table():
    out = score_open_orders()
    with psycopg.connect(get_settings().app_dsn) as c:
        rows = c.execute(
            "SELECT probability, risk_band FROM ml.delivery_risk").fetchall()
    assert len(rows) == out["scored"] >= 1
    for p, band in rows:
        assert 0 <= float(p) <= 1
        assert band in ("high", "medium", "low")


def test_agent_reader_can_select_but_not_write_ml():
    with psycopg.connect(get_settings().agent_dsn) as c:
        c.execute("SELECT count(*) FROM ml.delivery_risk").fetchone()
        c.execute("SELECT count(*) FROM ml.models").fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("TRUNCATE ml.delivery_risk")


def test_agent_answers_risk_question_through_ml_schema():
    from app.agent.graph import build_graph
    sql = ("SELECT po_number, supplier_name, probability, risk_band "
           "FROM ml.delivery_risk ORDER BY probability DESC LIMIT 5")
    llm = FakeMessagesListChatModel(responses=[
        AIMessage(f"```sql\n{sql}\n```"),
        AIMessage('```json\n{"chart_type": "table", "title": "Top risks"}\n```'),
        AIMessage("The riskiest open orders, ranked by model probability."),
    ])
    state = dict(BASE_STATE)
    state["question"] = "Which open orders have the highest late-delivery risk?"
    out = build_graph(llm).invoke(state)
    assert out["row_count"] >= 1
    assert "probability" in out["columns"]
    assert out["answer"]


def test_prediction_charts_update_live_on_rescoring():
    """A chart on ml.delivery_risk must refresh when scoring runs — model
    outputs are reactive data like any erp table."""
    from app.reactivity.engine import ReactivityEngine

    user_id = app_repo.create_user(
        f"ml-react-{uuid.uuid4().hex[:8]}@example.com", "x", "ML", "React",
        "Analyst", "IT", "analyst")["user_id"]
    chart = app_repo.create_saved_chart(
        user_id, "Live delivery risk",
        "SELECT po_number, probability FROM ml.delivery_risk "
        "ORDER BY probability DESC",
        {"chart_type": "table", "title": "Live delivery risk"})

    async def body():
        engine = ReactivityEngine(debounce=0.3)
        try:
            await engine.start()
            await asyncio.sleep(0.5)
            queue = engine.subscribe(user_id)
            await asyncio.to_thread(score_open_orders)
            payload = await _next_update_for(queue, chart["chart_id"])
            assert payload["source_tables"] == ["delivery_risk"]
            assert "probability" in payload["columns"]
        finally:
            await engine.stop()
            app_repo.delete_saved_chart(chart["chart_id"], user_id)

    asyncio.run(body())
