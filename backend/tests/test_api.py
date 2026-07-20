"""API integration tests: auth flow + chat persistence, with the agent
dependency overridden by a scripted fake-LLM graph (no API cost)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent.graph import build_graph
from app.agent.runner import AgentAnswer
from app.api.deps import get_ask
from app.main import create_app

pytestmark = pytest.mark.integration


def scripted_ask(question: str, tier: str = "fast") -> AgentAnswer:
    """Run the real graph + real DB with a scripted LLM."""
    llm = FakeMessagesListChatModel(responses=[
        AIMessage("```sql\nSELECT count(*) AS n FROM erp.projects\n```"),
        AIMessage('```json\n{"chart_type":"kpi","title":"Projets","value_field":"n"}\n```'),
        AIMessage("Il y a N projets."),
    ])
    out = build_graph(llm).invoke({
        "question": question, "schema_doc": "### erp.projects", "current_date": "2026-07-19"})
    return AgentAnswer(
        question=question, answer=out["answer"], sql=out["sql"],
        columns=out["columns"], rows=out["rows"], row_count=out["row_count"],
        truncated=out["truncated"], duration_ms=out["duration_ms"],
        attempts=out.get("attempts", []), chart=out.get("chart", {}), failed=False)


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_ask] = lambda: scripted_ask
    return TestClient(app)


@pytest.fixture()
def token(client: TestClient) -> str:
    email = f"test-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "s3cure-pass!", "display_name": "Testeur"})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": "s3cure-pass!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_register_login_and_auth_guard(client, token):
    assert client.get("/api/conversations").status_code == 401
    assert client.get("/api/conversations", headers=auth(token)).status_code == 200


def test_duplicate_email_conflict(client):
    body = {"email": "dup@example.com", "password": "s3cure-pass!",
            "display_name": "Dup"}
    client.post("/api/auth/register", json=body)
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_wrong_password_rejected(client, token):
    r = client.post("/api/auth/login", json={
        "email": "nobody@example.com", "password": "wrong-pass-123"})
    assert r.status_code == 401


def test_chat_creates_conversation_and_persists_turn(client, token):
    r = client.post("/api/chat", headers=auth(token),
                    json={"question": "Combien de projets au total ?"})
    assert r.status_code == 200, r.text
    payload = r.json()
    conv_id = payload["conversation_id"]
    am = payload["assistant_message"]
    assert am["role"] == "assistant"
    assert am["sql_query"].lower().startswith("select")
    assert am["chart"]["chart_type"] == "kpi"
    assert am["result_meta"]["row_count"] == 1
    assert am["result_meta"]["failed"] is False

    # follow-up in the same conversation + history read-back
    r2 = client.post("/api/chat", headers=auth(token),
                     json={"question": "Et encore ?", "conversation_id": conv_id})
    assert r2.status_code == 200
    msgs = client.get(f"/api/conversations/{conv_id}/messages",
                      headers=auth(token)).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]

    convs = client.get("/api/conversations", headers=auth(token)).json()
    assert any(c["conversation_id"] == conv_id for c in convs)

def test_chat_persists_decimal_and_date_types(client, token):
    """Regression: real ERP results carry Decimal (numeric) and date columns;
    persistence to jsonb must serialize them. Caught live by a real question,
    missed by count(*)-only test data — hence this representative-types test."""
    def decimal_ask(question: str, tier: str = "fast"):
        llm = FakeMessagesListChatModel(responses=[
            AIMessage("```sql\nSELECT po_number, total_amount, order_date "
                      "FROM erp.purchase_orders ORDER BY po_id LIMIT 3\n```"),
            AIMessage('```json\n{"chart_type":"table","title":"POs"}\n```'),
            AIMessage("Voici les commandes."),
        ])
        out = build_graph(llm).invoke({
            "question": question, "schema_doc": "x", "current_date": "2026-07-19"})
        return AgentAnswer(
            question=question, answer=out["answer"], sql=out["sql"],
            columns=out["columns"], rows=out["rows"], row_count=out["row_count"],
            truncated=out["truncated"], duration_ms=out["duration_ms"],
            attempts=[], chart=out.get("chart", {}), failed=False)

    app = create_app()
    app.dependency_overrides[get_ask] = lambda: decimal_ask
    c2 = TestClient(app)
    r = c2.post("/api/chat", headers=auth(token),
                json={"question": "Montre-moi 3 commandes avec montants et dates"})
    assert r.status_code == 200, r.text
    meta = r.json()["assistant_message"]["result_meta"]
    assert meta["row_count"] == 3
    assert isinstance(meta["preview_rows"][0][1], (int, float))   # Decimal -> float
    assert isinstance(meta["preview_rows"][0][2], str)            # date -> ISO string
    
def test_conversation_ownership_enforced(client, token):
    r = client.post("/api/chat", headers=auth(token), json={"question": "Question A ?"})
    conv_id = r.json()["conversation_id"]
    # second user cannot read or write into it
    email = f"intruder-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={
        "email": email, "password": "s3cure-pass!", "display_name": "Intrus"})
    tok2 = client.post("/api/auth/login", json={
        "email": email, "password": "s3cure-pass!"}).json()["access_token"]
    assert client.get(f"/api/conversations/{conv_id}/messages",
                      headers=auth(tok2)).status_code == 404
    assert client.post("/api/chat", headers=auth(tok2),
                       json={"question": "Vol ?", "conversation_id": conv_id}
                       ).status_code == 404
