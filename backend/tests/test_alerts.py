

def test_retention_purges_only_old_resolved():
    """The 7-month window deletes stale RESOLVED alerts; active and
    acknowledged ones are never purged, however old — a condition that
    still holds must stay visible."""
    import psycopg

    from app.config import get_settings
    from app.expert.engine import evaluate_all
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute("""
            INSERT INTO es.alerts (rule_code, entity_ref, severity, title,
                                   detail, context, status, resolved_at)
            VALUES ('TEST_OLD', 'ref-purge', 'info', 't', 'd', '{}',
                    'resolved', now() - interval '8 months'),
                   ('TEST_OLD', 'ref-keep-recent', 'info', 't', 'd', '{}',
                    'resolved', now() - interval '2 months')
            ON CONFLICT (rule_code, entity_ref) DO UPDATE
            SET status = EXCLUDED.status, resolved_at = EXCLUDED.resolved_at
        """)
        c.execute("""
            INSERT INTO es.alerts (rule_code, entity_ref, severity, title,
                                   detail, context, status, first_seen)
            VALUES ('TEST_OLD', 'ref-ack-ancient', 'warning', 't', 'd', '{}',
                    'acknowledged', now() - interval '3 years')
            ON CONFLICT (rule_code, entity_ref) DO UPDATE
            SET status = EXCLUDED.status
        """)
    out = evaluate_all()
    assert "purged" in out            # summary shape; the COUNT may belong
    # to a concurrent evaluator (live backend = second writer), so all
    # behavioral assertions below are on database STATE, not on out[...]
    with psycopg.connect(get_settings().app_dsn) as c:
        rows = {r[0] for r in c.execute(
            "SELECT entity_ref FROM es.alerts WHERE rule_code='TEST_OLD'")}
    assert "ref-purge" not in rows              # old resolved: gone
    assert "ref-keep-recent" not in rows or True  # may resolve-purge later
    assert "ref-ack-ancient" in rows            # acknowledged: immortal
    # ref-keep-recent must still exist (2 months < 7)
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        kept = c.execute("SELECT count(*) FROM es.alerts WHERE "
                         "entity_ref='ref-keep-recent'").fetchone()[0]
        assert kept == 1
        c.execute("DELETE FROM es.alerts WHERE rule_code='TEST_OLD'")


def test_critical_email_content(monkeypatch):
    """The critical-alert mail carries every new alert and reaches every
    decider — verified by capturing the SMTP handoff."""
    import smtplib

    from app.services import mailer
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): ...
        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]
            sent["body"] = msg.get_content()

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mailer.send_critical_alerts(
        ["boss@gets.tn", "chief@gets.tn"],
        [("TSS OTD collapse", "On-time rate 17% over trailing window")])
    assert "boss@gets.tn" in sent["to"] and "chief@gets.tn" in sent["to"]
    assert "1 new CRITICAL" in sent["subject"]
    assert "TSS OTD collapse" in sent["body"]


def _ensure_notified_manager(conn) -> str:
    """A manager on a REAL (non-RFC-2606) domain — the kind of account the
    notifier is allowed to email."""
    import uuid
    email = f"notify-mgr-{uuid.uuid4().hex[:8]}@supplyscope.local"
    conn.execute(
        "INSERT INTO app.users (email, password_hash, first_name, last_name,"
        " job_title, department, role, is_verified) "
        "VALUES (%s, 'x', 'Notify', 'Manager', 'PM', 'IT', 'manager', true)",
        (email,))
    return email


def test_engine_actually_sends_the_critical_email(monkeypatch):
    """INTEGRATION at the seam: not the mailer in isolation (already tested)
    but the engine's wiring to it — the exact gap where a row-format bug
    once hid behind a best-effort except. Deleting an existing critical
    forces it to re-fire as NEW on the next evaluation."""
    import psycopg

    from app.config import get_settings
    from app.expert import engine as eng
    s = get_settings()

    captured = {}

    def fake_send(recipients, alerts):
        captured["to"] = recipients
        captured["alerts"] = alerts

    monkeypatch.setattr("app.services.mailer.send_critical_alerts", fake_send)
    monkeypatch.setattr(s, "alert_email_enabled", True)

    out = None
    for _attempt in range(3):        # the live backend is a second writer:
        with psycopg.connect(s.app_dsn, autocommit=True) as c:
            mgr = _ensure_notified_manager(c)
            row = c.execute("SELECT rule_code, entity_ref FROM es.alerts "
                            "WHERE severity='critical' LIMIT 1").fetchone()
            assert row, "world should have at least one critical alert"
            c.execute("DELETE FROM es.alerts WHERE rule_code=%s "
                      "AND entity_ref=%s", row)
        out = eng.evaluate_all()
        if out["new_critical"] >= 1:
            break

    assert out["new_critical"] >= 1
    assert captured.get("to"), "engine never reached the mailer"
    assert mgr in captured["to"]
    # RFC 2606 fixtures never receive notifications
    assert not any("@example." in r for r in captured["to"])
    assert len(captured["alerts"]) == out["new_critical"]


def test_reactivated_alert_notifies_again(monkeypatch):
    """A condition that clears and RETURNS must notify again. Without this,
    a demo (or a real recurring problem) announces itself exactly once in
    the lifetime of the database and is silent forever after."""
    import psycopg

    from app.config import get_settings
    from app.expert import engine as eng
    s = get_settings()
    captured = {}
    monkeypatch.setattr("app.services.mailer.send_critical_alerts",
                        lambda r, a: captured.update(to=r, alerts=a))
    monkeypatch.setattr(s, "alert_email_enabled", True)
    out = None
    for _attempt in range(3):        # re-arm if a second writer stole the
        with psycopg.connect(s.app_dsn, autocommit=True) as c:  # transition
            row = c.execute("SELECT rule_code, entity_ref FROM es.alerts "
                            "WHERE severity='critical' LIMIT 1").fetchone()
            assert row
            c.execute("UPDATE es.alerts SET status='resolved', "
                      "resolved_at=now() WHERE rule_code=%s AND entity_ref=%s",
                      row)
            _ensure_notified_manager(c)
        out = eng.evaluate_all()
        if out["reactivated"] >= 1:
            break
    assert out["reactivated"] >= 1
    assert out["raised"] == out["new"] + out["reactivated"]
    assert out["new_critical"] >= 1          # re-fire counts for email
    assert captured.get("to")
