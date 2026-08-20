"""Registration and login, hardened (Phase 10).

Verification: when EMAIL_VERIFICATION_ENABLED, a registration stores a
HASHED 6-digit code with a 15-minute expiry and emails it (MailHog in the
docker stack); login is refused until /verify succeeds. The first account
(bootstrap admin) and all accounts when the flag is off are auto-verified.

Lockout: 5 failed passwords lock the account for 15 minutes (HTTP 423).
A successful login resets the counter. Codes and passwords are never
stored or logged in clear text.
"""
from __future__ import annotations

import datetime as dt
import secrets

import psycopg
from fastapi import APIRouter, HTTPException, status

from app.api import security
from app.api.schemas import (DEPARTMENTS, LoginRequest, RegisterRequest,
                             TokenResponse, UserOut, VerifyRequest)
from app.config import get_settings
from app.db import app_repo
from app.services.audit import audit
from app.services.mailer import send_verification

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_code(email: str) -> None:
    code = f"{secrets.randbelow(10**6):06d}"
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=get_settings().verification_ttl_minutes)
    app_repo.set_verification(email, security.hash_password(code), expires)
    send_verification(email, code)


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest) -> UserOut:
    first = app_repo.count_users() == 0
    role = "admin" if first else "analyst"
    if body.department not in DEPARTMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown department")
    verified = first or not get_settings().email_verification_enabled
    try:
        user = app_repo.create_user(
            body.email.lower(), security.hash_password(body.password),
            body.first_name.strip(), body.last_name.strip(),
            body.job_title.strip(), body.department, role,
            is_verified=verified)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    if not verified:
        _issue_code(user["email"])
    return UserOut(**user)


@router.post("/verify", response_model=TokenResponse)
def verify(body: VerifyRequest) -> TokenResponse:
    user = app_repo.get_user_by_email(body.email.lower())
    if user is None or user["is_verified"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to verify")
    exp = user["verification_expires"]
    if exp is None or exp < dt.datetime.now(dt.timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "Code expired — request a new one")
    if not security.verify_password(body.code, user["verification_code_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong code")
    app_repo.mark_verified(user["user_id"])
    return TokenResponse(access_token=security.create_token(user["user_id"]))


@router.post("/resend", status_code=204)
def resend(body: LoginRequest) -> None:
    """Re-send a code. Requires the password: an unauthenticated stranger
    must not be able to trigger email to an arbitrary address."""
    user = app_repo.get_user_by_email(body.email.lower())
    if (user and not user["is_verified"]
            and security.verify_password(body.password, user["password_hash"])):
        _issue_code(user["email"])
    # deliberately 204 either way: no account-existence oracle


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    s = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    user = app_repo.get_user_by_email(body.email.lower())
    if user and user["locked_until"] and user["locked_until"] > now:
        raise HTTPException(status.HTTP_423_LOCKED,
                            "Account temporarily locked — try again later")
    if user is None or not security.verify_password(body.password, user["password_hash"]):
        if user is not None:
            locked = app_repo.record_failed_login(
                user["user_id"], s.max_failed_logins, s.lockout_minutes)
            if locked:
                audit("login.locked", user["user_id"], email=body.email.lower())
                raise HTTPException(status.HTTP_423_LOCKED,
                                    "Too many attempts — account locked")
            audit("login.failed", user["user_id"])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user["is_verified"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")
    app_repo.reset_failed_logins(user["user_id"])
    audit("login.success", user["user_id"])
    return TokenResponse(access_token=security.create_token(user["user_id"]))
