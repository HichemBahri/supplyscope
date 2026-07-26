"""Pydantic request/response models for the HTTP API."""
from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, EmailStr, Field


DEPARTMENTS = ("Supply Chain", "Tendering", "Engineering",
               "Finance", "IT", "Management")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    job_title: str = Field(min_length=2, max_length=80)
    department: str = "Supply Chain"


class ProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=60)
    last_name: str | None = Field(default=None, min_length=1, max_length=60)
    job_title: str | None = Field(default=None, min_length=2, max_length=80)
    department: str | None = None


class AdminUserUpdate(ProfileUpdate):
    role: str | None = Field(default=None, pattern="^(admin|analyst)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str
    job_title: str
    department: str
    role: str
    has_avatar: bool
    created_at: dt.datetime


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    conversation_id: int | None = None
    tier: str = Field(default="fast", pattern="^(fast|smart)$")


class MessageOut(BaseModel):
    message_id: int
    role: str
    content: str
    sql_query: str | None = None
    chart: dict | None = None
    result_meta: dict | None = None
    created_at: dt.datetime


class ChatResponse(BaseModel):
    conversation_id: int
    user_message: MessageOut
    assistant_message: MessageOut


class ConversationOut(BaseModel):
    conversation_id: int
    title: str
    created_at: dt.datetime
    updated_at: dt.datetime


class SaveChartRequest(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    sql_query: str = Field(min_length=8, max_length=8000)
    chart_spec: dict


class SavedChartOut(BaseModel):
    chart_id: int
    title: str
    sql_query: str
    chart_spec: dict
    created_at: dt.datetime
    updated_at: dt.datetime


class ChartDataOut(BaseModel):
    chart_id: int
    chart_spec: dict
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: float

class DashboardCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class DashboardUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_shared: bool | None = None


class DashboardOut(BaseModel):
    dashboard_id: int
    owner_id: int
    title: str
    description: str | None
    is_shared: bool
    owner_first_name: str
    owner_last_name: str
    chart_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


class DashboardChartOut(BaseModel):
    chart_id: int
    title: str
    sql_query: str
    chart_spec: dict
    position: int


class DashboardDetail(DashboardOut):
    charts: list[DashboardChartOut]
    can_edit: bool


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    comment_id: int
    dashboard_id: int
    user_id: int
    content: str
    first_name: str
    last_name: str
    job_title: str
    has_avatar: bool
    created_at: dt.datetime
