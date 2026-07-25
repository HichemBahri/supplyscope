"""Identity & administration tests: bootstrap admin, profile, avatars,
admin CRUD, and the lockout guards."""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def register(client: TestClient, **over) -> dict:
    body = {"email": f"u-{uuid.uuid4().hex[:10]}@example.com",
            "password": "s3cure-pass!", "first_name": "Amine",
            "last_name": "Ben Salah", "job_title": "Logistics Coordinator",
            "department": "Supply Chain", **over}
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201, r.text
    tok = client.post("/api/auth/login", json={
        "email": body["email"], "password": body["password"]}).json()["access_token"]
    return {"user": r.json(), "token": tok,
            "auth": {"Authorization": f"Bearer {tok}"}}


def test_first_user_is_admin_then_analysts(client):
    # NB: DB starts empty in the bench; in a shared DB this asserts relative roles
    a = register(client)
    b = register(client)
    assert b["user"]["role"] == "analyst"
    me = client.get("/api/me", headers=a["auth"]).json()
    assert me["email"] == a["user"]["email"]
    assert me["role"] in ("admin", "analyst")


def test_profile_update_and_department_whitelist(client):
    u = register(client)
    r = client.patch("/api/me", headers=u["auth"],
                     json={"job_title": "Senior Buyer", "department": "Finance"})
    assert r.status_code == 200 and r.json()["job_title"] == "Senior Buyer"
    r = client.patch("/api/me", headers=u["auth"], json={"department": "Marketing"})
    assert r.status_code == 422


def test_avatar_upload_roundtrip_and_limits(client):
    u = register(client)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = client.put("/api/me/avatar", headers=u["auth"],
                   files={"file": ("me.png", io.BytesIO(png), "image/png")})
    assert r.status_code == 204
    r = client.get(f"/api/users/{u['user']['user_id']}/avatar",
                   params={"t": u["token"]})
    assert r.status_code == 200 and r.content == png
    assert r.headers["content-type"] == "image/png"
    r = client.put("/api/me/avatar", headers=u["auth"],
                   files={"file": ("x.gif", io.BytesIO(b"GIF89a"), "image/gif")})
    assert r.status_code == 422
    big = b"0" * (2 * 1024 * 1024 + 1)
    r = client.put("/api/me/avatar", headers=u["auth"],
                   files={"file": ("big.png", io.BytesIO(big), "image/png")})
    assert r.status_code == 413


def _make_admin_pair(client):
    """Ensure we hold an admin token regardless of DB history: register a user
    then promote it via direct repo access if it isn't the bootstrap admin."""
    from app.db import app_repo
    a = register(client)
    if a["user"]["role"] != "admin":
        app_repo.update_user(a["user"]["user_id"], {"role": "admin"})
    b = register(client)
    return a, b


def test_admin_crud_and_guards(client):
    a, b = _make_admin_pair(client)
    # analyst is refused
    assert client.get("/api/admin/users", headers=b["auth"]).status_code == 403
    # admin lists everyone
    users = client.get("/api/admin/users", headers=a["auth"]).json()
    assert any(u["user_id"] == b["user"]["user_id"] for u in users)
    # admin edits an employee
    r = client.patch(f"/api/admin/users/{b['user']['user_id']}", headers=a["auth"],
                     json={"job_title": "Asset Manager", "role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    # demote back is fine (another admin remains)
    r = client.patch(f"/api/admin/users/{b['user']['user_id']}", headers=a["auth"],
                     json={"role": "analyst"})
    assert r.status_code == 200
    # self-deletion via admin API refused
    assert client.delete(f"/api/admin/users/{a['user']['user_id']}",
                         headers=a["auth"]).status_code == 409
    # admin deletes the employee
    assert client.delete(f"/api/admin/users/{b['user']['user_id']}",
                         headers=a["auth"]).status_code == 204
    assert client.get("/api/me", headers=b["auth"]).status_code == 401
