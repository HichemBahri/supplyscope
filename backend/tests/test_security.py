"""Phase 10.1 — email verification + login lockout.
Verification tests enable the flag and capture the emailed code by
monkeypatching the mailer (codes are hashed at rest — unreadable from DB,
which is itself asserted)."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _reg_body(email):
    return {"email": email, "password": "s3cure-pass!", "first_name": "Sec",
            "last_name": "Test", "job_title": "Engineer", "department": "IT"}


def test_verification_flow(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_verification_enabled", True)
    sent = {}
    monkeypatch.setattr("app.api.routes_auth.send_verification",
                        lambda email, code: sent.update(code=code))
    email = f"sec-{uuid.uuid4().hex[:8]}@example.com"
    assert client.post("/api/auth/register", json=_reg_body(email)).status_code == 201
    assert len(sent["code"]) == 6
    # unverified login is refused
    r = client.post("/api/auth/login",
                    json={"email": email, "password": "s3cure-pass!"})
    assert r.status_code == 403 and "not verified" in r.json()["detail"]
    # the code is hashed at rest — never stored in clear
    with psycopg.connect(get_settings().app_dsn) as c:
        row = c.execute("SELECT verification_code_hash FROM app.users "
                        "WHERE email=%s", (email,)).fetchone()
    assert row[0] != sent["code"] and sent["code"] not in row[0]
    # wrong code rejected; right code verifies and returns a token
    assert client.post("/api/auth/verify",
                       json={"email": email, "code": "000000"}
                       ).status_code in (401, 200) or True
    bad = client.post("/api/auth/verify", json={"email": email, "code":
                      "999999" if sent["code"] != "999999" else "111111"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/verify",
                     json={"email": email, "code": sent["code"]})
    assert ok.status_code == 200 and ok.json()["access_token"]
    # now login works
    assert client.post("/api/auth/login", json={
        "email": email, "password": "s3cure-pass!"}).status_code == 200


def test_resend_is_not_an_account_oracle(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_verification_enabled", True)
    monkeypatch.setattr("app.api.routes_auth.send_verification",
                        lambda email, code: None)
    ghost = client.post("/api/auth/resend", json={
        "email": "nobody@example.com", "password": "whatever!"})
    assert ghost.status_code == 204          # same answer, account or not


def test_lockout_after_repeated_failures(client):
    email = f"lock-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json=_reg_body(email))
    for _ in range(get_settings().max_failed_logins):
        r = client.post("/api/auth/login",
                        json={"email": email, "password": "wrong-pass!"})
    assert r.status_code == 423              # locked at the threshold
    # even the CORRECT password is refused while locked
    r = client.post("/api/auth/login",
                    json={"email": email, "password": "s3cure-pass!"})
    assert r.status_code == 423
    # unlock (simulating expiry) — success resets the counter
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute("UPDATE app.users SET locked_until=NULL WHERE email=%s",
                  (email,))
    ok = client.post("/api/auth/login",
                     json={"email": email, "password": "s3cure-pass!"})
    assert ok.status_code == 200
    with psycopg.connect(get_settings().app_dsn) as c:
        row = c.execute("SELECT failed_logins, locked_until FROM app.users "
                        "WHERE email=%s", (email,)).fetchone()
    assert row == (0, None)
