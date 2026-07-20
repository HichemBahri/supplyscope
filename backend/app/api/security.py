"""Password hashing (bcrypt) and JWT issuance/verification."""
from __future__ import annotations

import datetime as dt

import bcrypt
import jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    s = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=s.jwt_expiry_hours),
        "iat": dt.datetime.now(dt.UTC),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> int:
    """Return user_id or raise jwt.PyJWTError."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    return int(payload["sub"])
