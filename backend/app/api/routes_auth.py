"""Registration and login. The first account ever created becomes admin
(bootstrap pattern: no hardcoded credentials); everyone after is an analyst
until an admin promotes them."""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, HTTPException, status

from app.api import security
from app.api.schemas import (DEPARTMENTS, LoginRequest, RegisterRequest,
                             TokenResponse, UserOut)
from app.db import app_repo

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest) -> UserOut:
    role = "admin" if app_repo.count_users() == 0 else "analyst"
    if body.department not in DEPARTMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown department")
    try:
        user = app_repo.create_user(
            body.email.lower(), security.hash_password(body.password),
            body.first_name.strip(), body.last_name.strip(),
            body.job_title.strip(), body.department, role)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return UserOut(**user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    user = app_repo.get_user_by_email(body.email.lower())
    if user is None or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenResponse(access_token=security.create_token(user["user_id"]))
