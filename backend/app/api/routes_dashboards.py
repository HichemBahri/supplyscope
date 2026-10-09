"""Collaborative dashboards: private collections of saved charts, publishable
team-wide by admins (read-only for viewers), with comments open to every
viewer and broadcast live over the SSE stream.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user, require_role
from app.api.schemas import (
    CommentCreate, CommentOut, DashboardCreate, DashboardDetail, DashboardOut,
    DashboardUpdate,
)
from app.db import app_repo
from app.services.audit import audit

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _load(dashboard_id: int) -> dict:
    dash = app_repo.get_dashboard(dashboard_id)
    if dash is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found")
    return dash


def _require_view(dash: dict, user: dict) -> None:
    if dash["owner_id"] != user["user_id"] and not dash["is_shared"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found")


def _require_owner(dash: dict, user: dict) -> None:
    if dash["owner_id"] != user["user_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner access required")


def _reindex(request: Request) -> None:
    if (engine := getattr(request.app.state, "reactivity", None)):
        engine.reindex_soon()


@router.post("", response_model=DashboardOut, status_code=201)
def create(body: DashboardCreate,
           user: dict = Depends(require_role("admin", "analyst"))) -> DashboardOut:
    d = app_repo.create_dashboard(user["user_id"], body.title, body.description)
    return DashboardOut(**d, owner_first_name=user["first_name"],
                        owner_last_name=user["last_name"], chart_count=0)


@router.get("", response_model=list[DashboardOut])
def list_all(user: dict = Depends(get_current_user)) -> list[DashboardOut]:
    return [DashboardOut(**d) for d in app_repo.list_dashboards_for(user["user_id"])]


@router.get("/{dashboard_id}", response_model=DashboardDetail)
def detail(dashboard_id: int, user: dict = Depends(get_current_user)) -> DashboardDetail:
    dash = _load(dashboard_id)
    _require_view(dash, user)
    charts = app_repo.dashboard_charts(dashboard_id)
    return DashboardDetail(
        **{k: dash[k] for k in ("dashboard_id", "owner_id", "title", "description",
                                "is_shared", "created_at", "updated_at",
                                "owner_first_name", "owner_last_name")},
        chart_count=len(charts),
        charts=charts,
        can_edit=dash["owner_id"] == user["user_id"])


@router.patch("/{dashboard_id}", response_model=DashboardOut)
def update(dashboard_id: int, body: DashboardUpdate, request: Request,
           user: dict = Depends(get_current_user)) -> DashboardOut:
    dash = _load(dashboard_id)
    _require_owner(dash, user)
    if body.is_shared is not None and user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Sharing with the whole team is an administrator action")
    updated = app_repo.update_dashboard(dashboard_id, body.model_dump())
    _reindex(request)   # shared-chart audience may have changed
    count = len(app_repo.dashboard_charts(dashboard_id))
    return DashboardOut(**updated, chart_count=count)


@router.delete("/{dashboard_id}", status_code=204)
def delete(dashboard_id: int, request: Request,
           user: dict = Depends(get_current_user)) -> None:
    dash = _load(dashboard_id)
    if user["role"] != "admin":          # admins moderate: they may remove any board
        _require_owner(dash, user)
    app_repo.delete_dashboard(dashboard_id)
    if dash["owner_id"] != user["user_id"]:
        audit("dashboard.deleted_by_admin", user["user_id"],
              dashboard_id=dashboard_id, owner_id=dash["owner_id"], title=dash["title"])
    _reindex(request)


@router.post("/{dashboard_id}/charts/{chart_id}", status_code=204)
def add_chart(dashboard_id: int, chart_id: int, request: Request,
              user: dict = Depends(get_current_user)) -> None:
    dash = _load(dashboard_id)
    _require_owner(dash, user)
    if app_repo.get_saved_chart(chart_id, user["user_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chart not found")
    app_repo.add_chart_to_dashboard(dashboard_id, chart_id)
    _reindex(request)


@router.delete("/{dashboard_id}/charts/{chart_id}", status_code=204)
def remove_chart(dashboard_id: int, chart_id: int, request: Request,
                 user: dict = Depends(get_current_user)) -> None:
    dash = _load(dashboard_id)
    _require_owner(dash, user)
    if not app_repo.remove_chart_from_dashboard(dashboard_id, chart_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chart not on this dashboard")
    _reindex(request)


# --------------------------------------------------------------- comments

@router.get("/{dashboard_id}/comments", response_model=list[CommentOut])
def comments(dashboard_id: int, user: dict = Depends(get_current_user)) -> list[CommentOut]:
    dash = _load(dashboard_id)
    _require_view(dash, user)
    return [CommentOut(**c) for c in app_repo.list_comments(dashboard_id)]


@router.post("/{dashboard_id}/comments", response_model=CommentOut, status_code=201)
def post_comment(dashboard_id: int, body: CommentCreate, request: Request,
                 user: dict = Depends(get_current_user)) -> CommentOut:
    dash = _load(dashboard_id)
    _require_view(dash, user)
    comment = app_repo.add_comment(dashboard_id, user["user_id"], body.content.strip())
    if (engine := getattr(request.app.state, "reactivity", None)):
        engine.broadcast_comment(comment)   # live to every connected employee
    return CommentOut(**comment)


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: int,
                   user: dict = Depends(get_current_user)) -> None:
    c = app_repo.get_comment(comment_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    if c["user_id"] != user["user_id"] and user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only the author or an administrator can delete a comment")
    app_repo.delete_comment(comment_id)


@router.post("/synthesize", status_code=201)
def synthesize(body: dict,
               user: dict = Depends(require_role("admin", "analyst"))) -> dict:
    """Agentic dashboard synthesis: topic in, live multi-chart dashboard out."""
    topic = (body.get("topic") or "").strip()
    if not (3 <= len(topic) <= 200):
        from fastapi import HTTPException
        raise HTTPException(422, "topic must be 3-200 characters")
    from app.agent.dashboard_synth import synthesize_dashboard
    return synthesize_dashboard(topic, user["user_id"])
