"""Current-user profile (me) and avatars."""
from __future__ import annotations

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status

from app.api.deps import get_current_user
from app.api.security import decode_token
from app.api.schemas import DEPARTMENTS, ProfileUpdate, UserOut
from app.db import app_repo

router = APIRouter(prefix="/api", tags=["users"])

MAX_AVATAR_BYTES = 2 * 1024 * 1024
ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(**user)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate,
              user: dict = Depends(get_current_user)) -> UserOut:
    if body.department is not None and body.department not in DEPARTMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown department")
    updated = app_repo.update_user(user["user_id"], body.model_dump())
    return UserOut(**updated)


@router.put("/me/avatar", status_code=204)
async def upload_avatar(file: UploadFile,
                        user: dict = Depends(get_current_user)) -> None:
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Use a PNG, JPEG or WebP image")
    data = await file.read()
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "Image too large (2 MB max)")
    app_repo.set_avatar(user["user_id"], data, file.content_type)


@router.get("/users/{user_id}/avatar")
def avatar(user_id: int, t: str) -> Response:
    """Avatar image. Auth via token query param: <img> tags cannot send an
    Authorization header (same workaround as the SSE stream, ADR-008)."""
    try:
        decode_token(t)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    row = app_repo.get_avatar(user_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No avatar")
    return Response(content=bytes(row["avatar"]), media_type=row["avatar_mime"],
                    headers={"Cache-Control": "private, max-age=60"})
