"""Phase 9 — the three-actor model. The matrix is deliberately non-nested:
managers acknowledge and consume, analysts produce, admins administer."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import psycopg

from app.config import get_settings
from app.expert.engine import evaluate_all
from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _user(client, role: str) -> tuple[str, int]:
    email = f"role-{role}-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={
        "email": email, "password": "s3cure-pass!", "first_name": "R",
        "last_name": role.title(), "job_title": "Engineer", "department": "IT"})
    if role != "analyst":
        with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
            c.execute("UPDATE app.users SET role = %s WHERE email = %s",
                      (role, email))
    tok = client.post("/api/auth/login", json={
        "email": email, "password": "s3cure-pass!"}).json()["access_token"]
    me = client.get("/api/me", headers=_h(tok)).json()
    return tok, me["user_id"]


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


GOOD = {"title": "Suppliers count", "sql_query": "SELECT count(*) AS n FROM erp.suppliers",
        "chart_spec": {"chart_type": "kpi", "title": "Suppliers", "value_field": "n"}}


def test_manager_role_is_assignable_and_persists(client):
    tok, uid = _user(client, "manager")
    me = client.get("/api/me", headers=_h(tok)).json()
    assert me["role"] == "manager"


def test_producers_can_save_charts_manager_cannot(client):
    a_tok, _ = _user(client, "analyst")
    m_tok, _ = _user(client, "manager")
    ok = client.post("/api/charts", headers=_h(a_tok), json=GOOD)
    assert ok.status_code == 201
    denied = client.post("/api/charts", headers=_h(m_tok), json=GOOD)
    assert denied.status_code == 403
    assert "admin or analyst" in denied.json()["detail"]
    client.delete(f"/api/charts/{ok.json()['chart_id']}", headers=_h(a_tok))


def test_manager_cannot_create_dashboard(client):
    m_tok, _ = _user(client, "manager")
    r = client.post("/api/dashboards", headers=_h(m_tok),
                    json={"title": "Q3 review"})
    assert r.status_code == 403


def test_only_deciders_can_acknowledge_alerts(client):
    evaluate_all()
    a_tok, _ = _user(client, "analyst")
    m_tok, _ = _user(client, "manager")
    alerts = client.get("/api/alerts?severity=critical", headers=_h(a_tok)).json()
    target = next(a for a in alerts if a["status"] == "active")
    denied = client.post(f"/api/alerts/{target['alert_id']}/ack", headers=_h(a_tok))
    assert denied.status_code == 403
    ok = client.post(f"/api/alerts/{target['alert_id']}/ack", headers=_h(m_tok))
    assert ok.status_code == 200
    # restore for other suites
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute("UPDATE es.alerts SET status='active', acknowledged_by=NULL,"
                  " acknowledged_at=NULL WHERE alert_id=%s",
                  (target["alert_id"],))


def test_manager_can_still_consume(client):
    m_tok, _ = _user(client, "manager")
    assert client.get("/api/alerts", headers=_h(m_tok)).status_code == 200
    assert client.get("/api/ml/predictions", headers=_h(m_tok)).status_code == 200
    assert client.get("/api/dashboards", headers=_h(m_tok)).status_code == 200
