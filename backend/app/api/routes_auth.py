"""Registration and login."""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, HTTPException, status

from app.api import security
from app.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.db import app_repo

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest) -> UserOut:
    try:
        user = app_repo.create_user(
            body.email.lower(), security.hash_password(body.password), body.display_name)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return UserOut(**user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    user = app_repo.get_user_by_email(body.email.lower())
    if user is None or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenResponse(access_token=security.create_token(user["user_id"]))
