"""Pydantic request/response models for the HTTP API."""
from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    user_id: int
    email: str
    display_name: str


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