"""Phase 8 — expert system: rule firing on the seeded world, alert
lifecycle (fire / persist-ack / resolve / re-fire), API, agent access."""
from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from app.config import get_settings
from app.expert.engine import ensure_ddl, evaluate_all


def _conn():
    return psycopg.connect(get_settings().app_dsn, row_factory=dict_row,
                           autocommit=True)


import uuid

from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    email = f"expert-{uuid.uuid4().hex[:10]}@example.com"
    client.post("/api/auth/register", json={
        "email": email, "password": "s3cure-pass!", "first_name": "Ex",
        "last_name": "Pert", "job_title": "Engineer", "department": "IT"})
    r = client.post("/api/auth/login",
                    json={"email": email, "password": "s3cure-pass!"})
    return r.json()["access_token"]


@pytest.fixture(scope="module", autouse=True)
def evaluated():
    ensure_ddl()
    return evaluate_all()


def test_known_seed42_conditions_fire(evaluated):
    with _conn() as c:
        rows = c.execute("SELECT rule_code, entity_ref, severity FROM es.alerts "
                         "WHERE status <> 'resolved'").fetchall()
    keys = {(r["rule_code"], r["entity_ref"]) for r in rows}
    assert ("SUPPLIER_LOW_OTD", "SUP-TSS") in keys          # story S1
    assert ("PROJECT_OVERBUDGET", "SOR2041") in keys        # story S4
    assert any(r["rule_code"] == "SHIPMENT_CUSTOMS_HOLD" for r in rows)
    assert all(r["severity"] in ("info", "warning", "critical") for r in rows)


def test_reevaluation_is_idempotent(evaluated):
    with _conn() as c:
        before = c.execute("SELECT count(*) AS n, min(first_seen) AS fs "
                           "FROM es.alerts").fetchone()
    s2 = evaluate_all()
    with _conn() as c:
        after = c.execute("SELECT count(*) AS n, min(first_seen) AS fs "
                          "FROM es.alerts").fetchone()
    assert s2["new"] == 0
    assert after["n"] == before["n"]
    assert after["fs"] == before["fs"]          # first_seen is stable


def test_resolve_and_refire_lifecycle():
    with _conn() as c:
        c.execute("""
            INSERT INTO es.alerts (rule_code, entity_ref, severity, title,
                                   detail) VALUES
            ('SUPPLIER_LOW_OTD', 'SUP-GHOST', 'critical', 'ghost', 'ghost')
            ON CONFLICT DO NOTHING""")
    evaluate_all()                               # ghost entity never fires
    with _conn() as c:
        row = c.execute("SELECT status, resolved_at FROM es.alerts WHERE "
                        "entity_ref = 'SUP-GHOST'").fetchone()
    assert row["status"] == "resolved" and row["resolved_at"] is not None
    # a resolved alert whose condition returns must reactivate: simulate by
    # marking a genuinely-firing alert resolved, then re-evaluating
    with _conn() as c:
        c.execute("UPDATE es.alerts SET status='resolved', resolved_at=now() "
                  "WHERE entity_ref = 'SUP-TSS'")
    evaluate_all()
    with _conn() as c:
        row = c.execute("SELECT status, resolved_at FROM es.alerts WHERE "
                        "entity_ref = 'SUP-TSS'").fetchone()
    assert row["status"] == "active" and row["resolved_at"] is None


def test_acknowledged_survives_reevaluation(client, token):
    # phase 9: acknowledging is a decider action — promote this user
    with _conn() as c:
        c.execute("UPDATE app.users SET role='manager' "
                  "WHERE email LIKE 'expert-%%'")
    r = client.get("/api/alerts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    target = next(a for a in r.json() if a["entity_ref"] == "SUP-TSS")
    r = client.post(f"/api/alerts/{target['alert_id']}/ack",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    evaluate_all()                               # condition still holds
    with _conn() as c:
        row = c.execute("SELECT status, acknowledged_by FROM es.alerts "
                        "WHERE alert_id = %s",
                        (target["alert_id"],)).fetchone()
    assert row["status"] == "acknowledged"       # not re-alarmed
    assert row["acknowledged_by"] is not None
    with _conn() as c:                           # restore for other tests
        c.execute("UPDATE es.alerts SET status='active', acknowledged_by=NULL,"
                  " acknowledged_at=NULL WHERE alert_id = %s",
                  (target["alert_id"],))


def test_api_summary_and_rules_and_filters(client, token):
    h = {"Authorization": f"Bearer {token}"}
    s = client.get("/api/alerts/summary", headers=h).json()
    assert s["critical"] >= 2 and s["total"] == (
        s["critical"] + s["warning"] + s["info"])
    rules = client.get("/api/alerts/rules", headers=h).json()
    assert len(rules) == 7
    crit = client.get("/api/alerts?severity=critical", headers=h).json()
    assert crit and all(a["severity"] == "critical" for a in crit)


def test_agent_reader_can_select_but_not_write():
    with psycopg.connect(get_settings().agent_dsn) as c:
        assert c.execute("SELECT count(*) FROM es.alerts").fetchone()[0] > 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM es.alerts")
