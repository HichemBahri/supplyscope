"""Supplier recommendation endpoints (Phase 11)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_role
from app.reco.engine import PRESETS, recommend
from app.services.audit import audit

router = APIRouter(prefix="/api/reco", tags=["recommendation"])


@router.get("/presets")
def presets(user: dict = Depends(get_current_user)) -> dict:
    return PRESETS


@router.get("/suppliers")
def suppliers(category: str, destination_country: str = "Tunisie",
              preset: str = "balanced", top_n: int = 5,
              w_technical: float | None = None, w_price: float | None = None,
              w_lead_time: float | None = None,
              w_reliability: float | None = None,
              w_quality: float | None = None, w_terms: float | None = None,
              w_ml_risk: float | None = None,
              user: dict = Depends(get_current_user)) -> dict:
    """Preset mode by default; any w_* parameter switches to custom-weight
    mode (the decision-maker's own preference vector, normalized server-side)."""
    supplied = {"technical": w_technical, "price": w_price,
                "lead_time": w_lead_time, "reliability": w_reliability,
                "quality": w_quality, "terms": w_terms, "ml_risk": w_ml_risk}
    custom = {k: v for k, v in supplied.items() if v is not None}
    try:
        return recommend(category, destination_country, preset,
                         min(top_n, 10), custom_weights=custom or None)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/decisions")
def record_decision(body: dict,
                    user: dict = Depends(require_role("admin", "manager"))
                    ) -> dict:
    """A decider records the outcome of a recommendation — approval or
    override — into the audit trail: the process closes its loop."""
    audit("reco.decision", user["user_id"],
          category=body.get("category"), preset=body.get("preset"),
          chosen_supplier=body.get("supplier_code"),
          top_ranked=body.get("top_ranked"),
          followed_recommendation=body.get("supplier_code")
                                  == body.get("top_ranked"))
    return {"recorded": True}
