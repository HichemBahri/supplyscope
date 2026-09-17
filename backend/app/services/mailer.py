"""Outbound email. In the docker stack this points at MailHog — a fake SMTP
server with a web inbox (http://localhost:8025) — so the verification email
is REAL and inspectable during a demo, without ever leaving the machine.
If SMTP is unreachable (bare dev), we log the code instead of crashing:
security features must never brick the login path in development.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("supplyscope.mailer")


def send_verification(email: str, code: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"] = "Your SupplyScope verification code"
    msg["From"] = s.mail_from
    msg["To"] = email
    msg.set_content(
        f"Your SupplyScope verification code is: {code}\n\n"
        f"It expires in {s.verification_ttl_minutes} minutes. "
        "If you did not create an account, ignore this email.")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=5) as smtp:
            smtp.send_message(msg)
    except OSError:
        logger.warning("SMTP unavailable — verification code for %s: %s",
                       email, code)


def send_critical_alerts(recipients: list[str],
                         alerts: list[tuple[str, str]]) -> None:
    """One email per evaluation batch, to every decider, listing the NEW
    critical alerts. Best-effort like all mail: an SMTP outage must never
    break the evaluation that detected the problem."""
    if not recipients or not alerts:
        return
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"] = (f"[SupplyScope] {len(alerts)} new CRITICAL "
                      f"alert{'s' if len(alerts) > 1 else ''}")
    msg["From"] = s.mail_from
    msg["To"] = ", ".join(recipients)
    lines = [f"- {title}\n  {detail}" for title, detail in alerts]
    msg.set_content(
        "The expert system has raised new critical alerts:\n\n"
        + "\n\n".join(lines)
        + "\n\nOpen the Alerts page to acknowledge them.")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=5) as smtp:
            smtp.send_message(msg)
    except OSError:
        logger.warning("SMTP unavailable — %d critical alert(s) not emailed",
                       len(alerts))
