"""Collaborative dashboards: ownership, admin-only sharing, viewer access,
comments, and both live-broadcast paths (comments + shared-chart updates)."""
from __future__ import annotations

import asyncio
import json
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import app_repo
from app.main import create_app
from app.reactivity.engine import ReactivityEngine

pytestmark = pytest.mark.integration


@pytest.fixture()
def client() -> TestClient:
    """Every dashboard created through this client is deleted at teardown,
    so test boards never linger in a shared database (they used to show up
    as ghost "Dana Karray" boards in the real interface)."""
    c = TestClient(create_app())
    created: list[int] = []
    real_post = c.post

    def tracking_post(url, *a, **kw):
        r = real_post(url, *a, **kw)
        if url == "/api/dashboards" and r.status_code == 201:
            created.append(r.json()["dashboard_id"])
        return r
    c.post = tracking_post          # type: ignore[method-assign]
    yield c
    for did in created:
        app_repo.delete_dashboard(did)


def register(client: TestClient, role: str | None = None) -> dict:
    body = {"email": f"d-{uuid.uuid4().hex[:10]}@example.com",
            "password": "s3cure-pass!", "first_name": "Dana",
            "last_name": "Karray", "job_title": "Buyer",
            "department": "Supply Chain"}
    u = client.post("/api/auth/register", json=body).json()
    if role and u["role"] != role:
        app_repo.update_user(u["user_id"], {"role": role})
    tok = client.post("/api/auth/login", json={
        "email": body["email"], "password": body["password"]}).json()["access_token"]
    return {"user": app_repo.get_user(u["user_id"]), "token": tok,
            "auth": {"Authorization": f"Bearer {tok}"}}


CHART = {"title": "POs by status",
         "sql_query": "SELECT status, count(*) AS n FROM erp.purchase_orders GROUP BY status",
         "chart_spec": {"chart_type": "bar", "title": "POs by status",
                        "x_field": "status", "y_fields": ["n"]}}


def test_dashboard_lifecycle_sharing_and_visibility(client):
    admin = register(client, role="admin")
    analyst = register(client)

    d = client.post("/api/dashboards", headers=admin["auth"],
                    json={"title": "Procurement overview"}).json()
    chart_id = client.post("/api/charts", headers=admin["auth"], json=CHART).json()["chart_id"]
    assert client.post(f"/api/dashboards/{d['dashboard_id']}/charts/{chart_id}",
                       headers=admin["auth"]).status_code == 204

    # private: invisible to the analyst (list + detail + chart data)
    assert all(x["dashboard_id"] != d["dashboard_id"]
               for x in client.get("/api/dashboards", headers=analyst["auth"]).json())
    assert client.get(f"/api/dashboards/{d['dashboard_id']}",
                      headers=analyst["auth"]).status_code == 404
    assert client.get(f"/api/charts/{chart_id}/data",
                      headers=analyst["auth"]).status_code == 404

    # analyst cannot share their own dashboard (admin action)
    own = client.post("/api/dashboards", headers=analyst["auth"],
                      json={"title": "My private board"}).json()
    assert client.patch(f"/api/dashboards/{own['dashboard_id']}",
                        headers=analyst["auth"],
                        json={"is_shared": True}).status_code == 403

    # admin shares -> analyst sees it, read-only, and can now fetch chart data
    assert client.patch(f"/api/dashboards/{d['dashboard_id']}", headers=admin["auth"],
                        json={"is_shared": True}).status_code == 200
    listed = client.get("/api/dashboards", headers=analyst["auth"]).json()
    assert any(x["dashboard_id"] == d["dashboard_id"] and x["is_shared"] for x in listed)
    detail = client.get(f"/api/dashboards/{d['dashboard_id']}",
                        headers=analyst["auth"]).json()
    assert detail["can_edit"] is False and len(detail["charts"]) == 1
    assert client.get(f"/api/charts/{chart_id}/data",
                      headers=analyst["auth"]).status_code == 200
    # ...but cannot modify it
    assert client.delete(f"/api/dashboards/{d['dashboard_id']}/charts/{chart_id}",
                         headers=analyst["auth"]).status_code == 403


def test_comments_flow_and_moderation(client):
    admin = register(client, role="admin")
    analyst = register(client)
    d = client.post("/api/dashboards", headers=admin["auth"],
                    json={"title": "Shared KPIs"}).json()
    client.patch(f"/api/dashboards/{d['dashboard_id']}", headers=admin["auth"],
                 json={"is_shared": True})

    c1 = client.post(f"/api/dashboards/{d['dashboard_id']}/comments",
                     headers=analyst["auth"],
                     json={"content": "Customs delays look worrying this quarter."})
    assert c1.status_code == 201
    assert c1.json()["first_name"] == "Dana"

    got = client.get(f"/api/dashboards/{d['dashboard_id']}/comments",
                     headers=admin["auth"]).json()
    assert [c["comment_id"] for c in got] == [c1.json()["comment_id"]]

    # a third analyst cannot delete someone else's comment; admin can
    other = register(client)
    cid = c1.json()["comment_id"]
    assert client.delete(f"/api/dashboards/comments/{cid}",
                         headers=other["auth"]).status_code == 403
    assert client.delete(f"/api/dashboards/comments/{cid}",
                         headers=admin["auth"]).status_code == 204


def test_comment_broadcast_reaches_all_subscribers(client):
    admin = register(client, role="admin")
    viewer = register(client)
    d = client.post("/api/dashboards", headers=admin["auth"],
                    json={"title": "Live board"}).json()
    client.patch(f"/api/dashboards/{d['dashboard_id']}", headers=admin["auth"],
                 json={"is_shared": True})

    async def body():
        engine = ReactivityEngine(debounce=0.2)
        await engine.start()
        try:
            q = engine.subscribe(viewer["user"]["user_id"])
            comment = app_repo.add_comment(d["dashboard_id"],
                                           admin["user"]["user_id"], "Live?")
            engine.broadcast_comment(comment)
            item = await asyncio.wait_for(q.get(), timeout=3)
            assert item["event"] == "comment_added"
            data = json.loads(item["data"])
            assert data["content"] == "Live?" and data["dashboard_id"] == d["dashboard_id"]
        finally:
            await engine.stop()

    asyncio.run(body())


def test_shared_chart_update_reaches_non_owner(client):
    """The headline behavior: a chart on a SHARED dashboard pushes live
    updates to employees who do not own it."""
    admin = register(client, role="admin")
    viewer = register(client)
    chart_id = client.post("/api/charts", headers=admin["auth"], json={
        "title": "Clients count",
        "sql_query": "SELECT count(*) AS n FROM erp.clients",
        "chart_spec": {"chart_type": "kpi", "title": "Clients count", "value_field": "n"},
    }).json()["chart_id"]
    d = client.post("/api/dashboards", headers=admin["auth"],
                    json={"title": "Team board"}).json()
    client.post(f"/api/dashboards/{d['dashboard_id']}/charts/{chart_id}",
                headers=admin["auth"])
    client.patch(f"/api/dashboards/{d['dashboard_id']}", headers=admin["auth"],
                 json={"is_shared": True})

    async def body():
        engine = ReactivityEngine(debounce=0.3)
        await engine.start()
        code = f"CL-S{uuid.uuid4().hex[:6].upper()}"
        try:
            await asyncio.sleep(0.4)
            q = engine.subscribe(viewer["user"]["user_id"])   # NOT the owner
            with psycopg.connect(get_settings().app_dsn, autocommit=True) as w:
                w.execute("INSERT INTO erp.clients (client_code,name,country,sector) "
                          "VALUES (%s,'Shared Probe','Tunisie','oil_gas')", (code,))
            from tests.test_reactivity import _next_update_for
            data = await _next_update_for(q, chart_id)
            assert data["chart_id"] == chart_id
        finally:
            await engine.stop()
            with psycopg.connect(get_settings().app_dsn, autocommit=True) as w:
                w.execute("DELETE FROM erp.clients WHERE client_code = %s", (code,))

    asyncio.run(body())


def test_admin_can_delete_any_dashboard_and_owner_cannot_delete_others(client):
    admin = register(client, role="admin")
    a1, a2 = register(client), register(client)
    d = client.post("/api/dashboards", headers=a1["auth"],
                    json={"title": "a1 board"}).json()
    # another analyst is refused
    assert client.delete(f"/api/dashboards/{d['dashboard_id']}",
                         headers=a2["auth"]).status_code == 403
    # the administrator may remove it (moderation), and it is audited
    assert client.delete(f"/api/dashboards/{d['dashboard_id']}",
                         headers=admin["auth"]).status_code == 204
    assert client.get(f"/api/dashboards/{d['dashboard_id']}",
                      headers=a1["auth"]).status_code == 404
    rows = client.get("/api/admin/audit", headers=admin["auth"],
                      params={"action": "dashboard.deleted_by_admin"}).json()
    assert any(r["detail"].get("dashboard_id") == d["dashboard_id"] for r in rows)
