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
