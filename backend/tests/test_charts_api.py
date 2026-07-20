"""Saved-charts API tests: validation-on-save, refresh, ownership, delete."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture()
def token(client: TestClient) -> str:
    email = f"charts-{uuid.uuid4().hex[:10]}@example.com"
    client.post("/api/auth/register", json={
        "email": email, "password": "s3cure-pass!", "display_name": "Chartiste"})
    return client.post("/api/auth/login", json={
        "email": email, "password": "s3cure-pass!"}).json()["access_token"]


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


GOOD = {
    "title": "Projets par statut",
    "sql_query": "SELECT status, count(*) AS n FROM erp.projects GROUP BY status",
    "chart_spec": {"chart_type": "bar", "title": "Projets par statut",
                   "x_field": "status", "y_fields": ["n"]},
}


def test_save_list_refresh_delete_cycle(client, token):
    r = client.post("/api/charts", headers=auth(token), json=GOOD)
    assert r.status_code == 201, r.text
    chart_id = r.json()["chart_id"]

    charts = client.get("/api/charts", headers=auth(token)).json()
    assert any(c["chart_id"] == chart_id for c in charts)

    r = client.get(f"/api/charts/{chart_id}/data", headers=auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["columns"] == ["status", "n"]
    assert data["chart_spec"]["chart_type"] == "bar"

    assert client.delete(f"/api/charts/{chart_id}",
                         headers=auth(token)).status_code == 204
    assert client.get(f"/api/charts/{chart_id}/data",
                      headers=auth(token)).status_code == 404


def test_save_rejects_bad_sql(client, token):
    body = dict(GOOD, sql_query="DELETE FROM erp.projects")
    r = client.post("/api/charts", headers=auth(token), json=body)
    assert r.status_code == 422 and "rejected" in r.json()["detail"]


def test_save_rejects_spec_column_mismatch(client, token):
    body = dict(GOOD, chart_spec={"chart_type": "bar", "title": "Statut invalide",
                                  "x_field": "statuss", "y_fields": ["n"]})
    r = client.post("/api/charts", headers=auth(token), json=body)
    assert r.status_code == 422 and "non-existent result columns" in r.json()["detail"]


def test_charts_are_private(client, token):
    chart_id = client.post("/api/charts", headers=auth(token),
                           json=GOOD).json()["chart_id"]
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={
        "email": email, "password": "s3cure-pass!", "display_name": "Autre"})
    tok2 = client.post("/api/auth/login", json={
        "email": email, "password": "s3cure-pass!"}).json()["access_token"]
    assert client.get(f"/api/charts/{chart_id}/data",
                      headers=auth(tok2)).status_code == 404
    assert client.delete(f"/api/charts/{chart_id}",
                         headers=auth(tok2)).status_code == 404
    # and the rightful owner still has it
    assert client.get(f"/api/charts/{chart_id}/data",
                      headers=auth(token)).status_code == 200
