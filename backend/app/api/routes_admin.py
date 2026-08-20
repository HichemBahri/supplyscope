"""Admin-only employee management (full CRUD on accounts).

Guards: admins only; an admin cannot delete their own account from here; the
last remaining admin can be neither deleted nor demoted (lockout protection).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.api.schemas import DEPARTMENTS, AdminUserUpdate, UserOut
from app.db import app_repo

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(_admin: dict = Depends(require_admin)) -> list[UserOut]:
    return [UserOut(**u) for u in app_repo.list_users()]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: AdminUserUpdate,
                admin: dict = Depends(require_admin)) -> UserOut:
    target = app_repo.get_user(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if body.department is not None and body.department not in DEPARTMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown department")
    if (body.role in ("analyst", "manager") and target["role"] == "admin"
            and app_repo.count_admins(excluding=user_id) == 0):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Cannot demote the last administrator")
    return UserOut(**app_repo.update_user(user_id, body.model_dump()))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: dict = Depends(require_admin)) -> None:
    if user_id == admin["user_id"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Delete your own account from your profile, not here")
    target = app_repo.get_user(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target["role"] == "admin" and app_repo.count_admins(excluding=user_id) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Cannot delete the last administrator")
    app_repo.delete_user(user_id)
