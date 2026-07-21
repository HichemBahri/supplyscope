"""SupplyScope API application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_auth, routes_charts, routes_chat, routes_stream
from app.reactivity.engine import ReactivityEngine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = ReactivityEngine()
    app.state.reactivity = engine
    await engine.start()
    try:
        yield
    finally:
        await engine.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="SupplyScope API", version="0.4.0",
                  description="Agentic analytics for EPC supply chain data.",
                  lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server (Phase 5)
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_auth.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_charts.router)
    app.include_router(routes_stream.router)

    @app.get("/api/health", tags=["ops"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
