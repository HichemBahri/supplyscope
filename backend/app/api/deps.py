"""FastAPI dependencies: current user, and the injectable agent callable."""
from __future__ import annotations

from typing import Callable

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agent.runner import AgentAnswer, ask
from app.api.security import decode_token
from app.db import app_repo

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        user_id = decode_token(creds.credentials)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = app_repo.get_user(user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


AskFn = Callable[..., AgentAnswer]


def get_ask() -> AskFn:
    """The agent entrypoint as a dependency, so tests can override it with a
    scripted fake-LLM graph (zero API cost)."""
    return ask
