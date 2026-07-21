"""Server-Sent Events stream of chart updates (ADR-008).

Browsers' EventSource cannot set an Authorization header, so the JWT is
passed as a query parameter and validated manually — the standard SSE
workaround (documented trade-off: tokens may appear in server logs; a
production system would mint short-lived stream tickets).
"""
from __future__ import annotations

import asyncio

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.security import decode_token
from app.db import app_repo

router = APIRouter(prefix="/api", tags=["stream"])

KEEPALIVE_SECONDS = 15


@router.get("/charts/stream")
async def chart_stream(request: Request, token: str) -> StreamingResponse:
    try:
        user_id = decode_token(token)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if app_repo.get_user(user_id) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")

    engine = request.app.state.reactivity
    queue = engine.subscribe(user_id)

    async def stream():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    payload = await asyncio.wait_for(
                        queue.get(), timeout=KEEPALIVE_SECONDS)
                    yield f"event: chart_update\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            engine.unsubscribe(user_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
