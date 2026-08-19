"""Reactivity engine tests, joint by joint:
1. DB triggers actually emit NOTIFY on writes.
2. Dependency extraction from chart SQL.
3. Index maps table changes to the right charts.
4. End-to-end async: write -> notify -> debounce -> refresh -> queue push.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import psycopg
import pytest

from app.config import get_settings
from app.db import app_repo
from app.reactivity.deps_index import ChartIndex, extract_tables
from app.reactivity.engine import ReactivityEngine

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- helpers

def _admin() -> psycopg.Connection:
    return psycopg.connect(get_settings().app_dsn, autocommit=True)


def _mk_user() -> int:
    return app_repo.create_user(
        f"react-{uuid.uuid4().hex[:10]}@example.com", "x", "React", "User",
        "Analyst", "IT", "analyst")["user_id"]


def _mk_chart(user_id: int) -> dict:
    return app_repo.create_saved_chart(
        user_id, "Nb clients",
        "SELECT count(*) AS n FROM erp.clients", 
        {"chart_type": "kpi", "title": "Nb clients", "value_field": "n"})


def _insert_probe_client(c: psycopg.Connection) -> str:
    code = f"CL-T{uuid.uuid4().hex[:6].upper()}"
    c.execute("INSERT INTO erp.clients (client_code,name,country,sector) "
              "VALUES (%s,'Probe Client','Tunisie','oil_gas')", (code,))
    return code


def _delete_probe_client(c: psycopg.Connection, code: str) -> None:
    c.execute("DELETE FROM erp.clients WHERE client_code = %s", (code,))


# ------------------------------------------------------------------ tests

def test_triggers_emit_notify_on_write():
    with _admin() as listener, _admin() as writer:
        listener.execute("LISTEN erp_data_change")
        code = _insert_probe_client(writer)
        try:
            got = [json.loads(n.payload)["table"]
                   for n in listener.notifies(timeout=3, stop_after=1)]
            assert got == ["clients"]
        finally:
            _delete_probe_client(writer, code)


def test_extract_tables():
    sql = ("SELECT s.name, count(*) FROM erp.shipments sh "
           "JOIN erp.purchase_orders po USING (po_id) "
           "JOIN ERP.Suppliers s ON s.supplier_id = po.supplier_id")
    assert extract_tables(sql) == {"shipments", "purchase_orders", "suppliers"}


def test_index_maps_tables_to_charts():
    user_id = _mk_user()
    chart = _mk_chart(user_id)
    try:
        idx = ChartIndex()
        idx.rebuild()
        hits = [c["chart_id"] for c in idx.charts_for({"clients"})]
        assert chart["chart_id"] in hits
        assert idx.charts_for({"maintenance_events"}) == [] or all(
            c["chart_id"] != chart["chart_id"]
            for c in idx.charts_for({"maintenance_events"}))
    finally:
        app_repo.delete_saved_chart(chart["chart_id"], user_id)




async def _next_update_for(queue, chart_id: int, timeout: float = 8.0):
    """Drain the broadcast queue until the update for chart_id arrives.

    On a broadcast bus, other listeners' charts may legitimately produce
    events first (e.g. shared charts from earlier data); asserting on the
    first event makes tests order-dependent."""
    import asyncio as _a, json as _j
    deadline = _a.get_event_loop().time() + timeout
    while True:
        remaining = deadline - _a.get_event_loop().time()
        item = await _a.wait_for(queue.get(), timeout=max(0.1, remaining))
        if item["event"] != "chart_update":
            continue
        data = _j.loads(item["data"])
        if data["chart_id"] == chart_id:
            return data

def test_end_to_end_write_to_subscriber_push():
    async def body():
        user_id = _mk_user()
        chart = _mk_chart(user_id)
        engine = ReactivityEngine(debounce=0.3)
        code = None
        try:
            await engine.start()
            await asyncio.sleep(0.5)          # let LISTEN establish
            queue = engine.subscribe(user_id)
            with _admin() as w:
                code = _insert_probe_client(w)
            payload = await _next_update_for(queue, chart["chart_id"])
            assert payload["columns"] == ["n"]
            # containment, not equality: background rule evaluation may
            # legitimately batch alert writes into the same debounce window
            assert "clients" in payload["source_tables"]
            assert payload["row_count"] == 1
        finally:
            await engine.stop()
            if code:
                with _admin() as w:
                    _delete_probe_client(w, code)
            app_repo.delete_saved_chart(chart["chart_id"], user_id)

    asyncio.run(body())


def test_save_chart_reindexes_from_sync_endpoint_with_lifespan():
    """Regression (found live): saving a chart via the sync HTTP endpoint —
    with the app lifespan actually running, i.e. TestClient in a with-block —
    must not crash and must get the chart into the engine index.

    The original bug: reindex_soon() used asyncio.get_running_loop() from a
    threadpool worker (no loop there) -> 500. Also a test-design lesson: the
    rest of the API tests skip lifespan, so app.state.reactivity never
    existed and the defensive getattr hid the broken path.
    """
    import time
    from fastapi.testclient import TestClient
    from app.main import create_app

    GOOD = {"title": "Commandes par statut",
            "sql_query": "SELECT status, count(*) AS n "
                         "FROM erp.purchase_orders GROUP BY status",
            "chart_spec": {"chart_type": "bar", "title": "Commandes par statut",
                           "x_field": "status", "y_fields": ["n"]}}

    with TestClient(create_app()) as client:      # with-block => lifespan runs
        email = f"lifespan-{uuid.uuid4().hex[:8]}@example.com"
        client.post("/api/auth/register", json={"email": email, "password": "s3cure-pass!", "first_name": "Test",
        "last_name": "User", "job_title": "Procurement Engineer",
        "department": "Supply Chain"})
        tok = client.post("/api/auth/login", json={
            "email": email, "password": "s3cure-pass!"}).json()["access_token"]
        r = client.post("/api/charts", headers={"Authorization": f"Bearer {tok}"},
                        json=GOOD)
        assert r.status_code == 201, r.text        # was 500 before the fix
        chart_id = r.json()["chart_id"]

        engine = client.app.state.reactivity
        for _ in range(20):                        # daemon thread: poll briefly
            if any(c["chart_id"] == chart_id
                   for c in engine.index.charts_for({"purchase_orders"})):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("chart not indexed after reindex_soon()")

        client.delete(f"/api/charts/{chart_id}",
                      headers={"Authorization": f"Bearer {tok}"})
