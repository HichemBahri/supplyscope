"""ML endpoints: model registry, predictions, and admin train/score actions.

Training and scoring run synchronously (seconds on this data volume); FastAPI
executes sync def endpoints in its threadpool, so the event loop — and with it
the SSE reactivity engine — never blocks.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.api.routes_admin import require_admin
from app.ml.registry import list_models
from app.ml.scoring import score_open_orders

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/models")
def models(user: dict = Depends(get_current_user)) -> list[dict]:
    return [dict(m) for m in list_models()]


@router.get("/predictions")
def predictions(user: dict = Depends(get_current_user)) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row
    from app.config import get_settings
    with psycopg.connect(get_settings().app_dsn, row_factory=dict_row) as c:
        return c.execute(
            "SELECT * FROM ml.delivery_risk ORDER BY probability DESC"
        ).fetchall()


@router.post("/train")
def train_endpoint(user: dict = Depends(require_admin)) -> dict:
    from app.ml.train_risk import train
    entry = train(verbose=False)
    return {"model_name": entry["model_name"], "version": entry["version"],
            "algo": entry["algo"], "metrics": entry["metrics"]}


@router.post("/score")
def score_endpoint(user: dict = Depends(require_admin)) -> dict:
    try:
        return score_open_orders()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
