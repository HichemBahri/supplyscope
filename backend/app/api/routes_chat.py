"""Chat endpoint: question in, persisted agent turn out. Plus history reads."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AskFn, get_ask, get_current_user
from app.api.schemas import (
    ChatRequest, ChatResponse, ConversationOut, MessageOut,
)
from app.db import app_repo

router = APIRouter(prefix="/api", tags=["chat"])

_PREVIEW_ROWS = 50


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest,
         user: dict = Depends(get_current_user),
         ask: AskFn = Depends(get_ask)) -> ChatResponse:
    # conversation: reuse (with ownership check) or create from the question
    if body.conversation_id is not None:
        conv = app_repo.get_conversation(body.conversation_id, user["user_id"])
        if conv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        conversation_id = conv["conversation_id"]
    else:
        title = body.question.strip()[:80]
        conversation_id = app_repo.create_conversation(
            user["user_id"], title)["conversation_id"]

    user_msg = app_repo.add_message(conversation_id, "user", body.question)

    result = ask(body.question, tier=body.tier)  # the agent turn

    result_meta = {
        "columns": result.columns,
        "preview_rows": result.rows[:_PREVIEW_ROWS],
        "row_count": result.row_count,
        "truncated": result.truncated or result.row_count > _PREVIEW_ROWS,
        "duration_ms": result.duration_ms,
        "attempts": result.attempts,
        "failed": result.failed,
    }
    assistant_msg = app_repo.add_message(
        conversation_id, "assistant", result.answer,
        sql_query=result.sql or None,
        chart=result.chart or None,
        result_meta=result_meta)
    app_repo.touch_conversation(conversation_id)

    return ChatResponse(
        conversation_id=conversation_id,
        user_message=MessageOut(**user_msg),
        assistant_message=MessageOut(**assistant_msg))


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(user: dict = Depends(get_current_user)) -> list[ConversationOut]:
    return [ConversationOut(**c) for c in app_repo.list_conversations(user["user_id"])]


@router.get("/conversations/{conversation_id}/messages",
            response_model=list[MessageOut])
def messages(conversation_id: int,
             user: dict = Depends(get_current_user)) -> list[MessageOut]:
    if app_repo.get_conversation(conversation_id, user["user_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return [MessageOut(**m) for m in app_repo.list_messages(conversation_id)]
