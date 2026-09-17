"""Phase 11 — supplier recommendation: process eligibility, explainable
scoring, preset sensitivity, decision audit."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.reco.engine import recommend


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _tok(client, role="analyst"):
    email = f"reco-{role}-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={
        "email": email, "password": "s3cure-pass!", "first_name": "R",
        "last_name": "Eco", "job_title": "Engineer", "department": "IT"})
    if role != "analyst":
        with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
            c.execute("UPDATE app.users SET role=%s WHERE email=%s",
                      (role, email))
    return client.post("/api/auth/login", json={
        "email": email, "password": "s3cure-pass!"}).json()["access_token"]


def test_scores_decompose_and_rank():
    out = recommend("steel", preset="balanced")
    cands = out["candidates"]
    assert len(cands) >= 3 and out["ml_risk_included"]
    scores = [c["score"] for c in cands]
    assert scores == sorted(scores, reverse=True)
    for c in cands:                     # the story behind the choice, exactly
        assert abs(sum(b["contribution"] for b in c["breakdown"])
                   - c["score"]) < 1e-6
    assert abs(sum(out["weights"].values()) - 1.0) < 1e-6


def test_tss_cheap_but_never_first():
    """Story S1 as a decision: perfect price cannot buy back an 83% late
    rate under any provided preset."""
    for preset in ("balanced", "cost_focused", "schedule_focused"):
        out = recommend("steel", preset=preset)
        by_code = {c["supplier_code"]: c for c in out["candidates"]}
        assert "SUP-TSS" in by_code                    # eligible (TBE-wise)
        tss = by_code["SUP-TSS"]
        assert out["candidates"][0]["supplier_code"] != "SUP-TSS"
        price = next(b for b in tss["breakdown"] if b["criterion"] == "price")
        assert price["normalized"] == 1.0              # the cheapest, always


def test_presets_change_the_ranking_or_scores():
    a = recommend("steel", preset="balanced")["candidates"]
    b = recommend("steel", preset="cost_focused")["candidates"]
    assert ([c["supplier_code"] for c in a] != [c["supplier_code"] for c in b]
            or any(abs(x["score"] - y["score"]) > 0.02
                   for x, y in zip(a, b)))


def test_api_read_for_all_decision_for_deciders(client):
    analyst, manager = _tok(client), _tok(client, "manager")
    h = lambda t: {"Authorization": f"Bearer {t}"}          # noqa: E731
    r = client.get("/api/reco/suppliers?category=steel", headers=h(analyst))
    assert r.status_code == 200 and r.json()["candidates"]
    top = r.json()["candidates"][0]["supplier_code"]
    body = {"category": "steel", "preset": "balanced",
            "supplier_code": top, "top_ranked": top}
    assert client.post("/api/reco/decisions", json=body,
                       headers=h(analyst)).status_code == 403
    assert client.post("/api/reco/decisions", json=body,
                       headers=h(manager)).status_code == 200
    with psycopg.connect(get_settings().app_dsn) as c:
        row = c.execute("SELECT detail FROM app.audit_log WHERE "
                        "action='reco.decision' ORDER BY audit_id DESC "
                        "LIMIT 1").fetchone()
    assert row[0]["followed_recommendation"] is True


def test_custom_weights_normalize_and_decompose():
    """Sliders can never break the invariant: any non-negative vector is
    normalized to sum 1.0 and contributions still sum to the score."""
    out = recommend("steel", custom_weights={"price": 3.0, "reliability": 1.0})
    assert out["preset"] == "custom"
    assert abs(sum(out["weights"].values()) - 1.0) < 1e-9
    assert abs(out["weights"]["price"] - 0.75) < 1e-9
    for c in out["candidates"]:
        assert abs(sum(b["contribution"] for b in c["breakdown"])
                   - c["score"]) < 1e-6


def test_custom_weights_matching_preset_reproduce_it():
    from app.reco.engine import PRESETS
    a = recommend("steel", preset="balanced")["candidates"]
    b = recommend("steel", custom_weights=dict(PRESETS["balanced"]))["candidates"]
    assert [c["supplier_code"] for c in a] == [c["supplier_code"] for c in b]
    assert all(abs(x["score"] - y["score"]) < 1e-9 for x, y in zip(a, b))


def test_pure_price_weighting_finally_crowns_tss():
    """The decision-maker's freedom is real: declare that ONLY price matters
    and the cheapest supplier (SUP-TSS) must rank first — the system obeys
    the preference instead of overriding it."""
    out = recommend("steel", custom_weights={"price": 1.0})
    assert out["candidates"][0]["supplier_code"] == "SUP-TSS"


def test_invalid_custom_weights_rejected(client):
    tok = _tok(client)
    h = {"Authorization": f"Bearer {tok}"}
    r = client.get("/api/reco/suppliers?category=steel&w_price=-1", headers=h)
    assert r.status_code == 422
    ok = client.get("/api/reco/suppliers?category=steel&w_price=2&w_quality=1",
                    headers=h)
    assert ok.status_code == 200 and ok.json()["preset"] == "custom"
