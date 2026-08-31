"""Procurement award optimization endpoints (Phase 12)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.optimize.engine import optimize_awards

router = APIRouter(prefix="/api/optimize", tags=["optimization"])


@router.get("/awards")
def awards(budget_tnd: float | None = None, penalty_rate: float = 0.15,
           max_supplier_share: float = 0.40, risk_ceiling: float = 0.65,
           since: str = "2026-01-01",
           user: dict = Depends(get_current_user)) -> dict:
    if not (0.0 <= penalty_rate <= 1.0) or not (0.05 <= max_supplier_share <= 1.0):
        raise HTTPException(422, "penalty_rate in [0,1]; share in [0.05,1]")
    if not (0.1 <= risk_ceiling <= 1.0):
        raise HTTPException(422, "risk_ceiling in [0.1, 1.0]")
    return optimize_awards(budget_tnd, penalty_rate, max_supplier_share,
                           risk_ceiling, since)
