"""SupplyScope API application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_auth, routes_charts, routes_chat


def create_app() -> FastAPI:
    app = FastAPI(title="SupplyScope API", version="0.3.0",
                  description="Agentic analytics for EPC supply chain data.")
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

    @app.get("/api/health", tags=["ops"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
