"""Supplier recommendation (Phase 11) — explainable multi-criteria decision
analysis grounded in the EPC procurement process.

Method: Simple Additive Weighting (SAW), a standard MCDA technique chosen
deliberately over black-box learning: every ranking decomposes into
per-criterion contributions a procurement officer can audit.

The pipeline mirrors the real process:
1. HARD ELIGIBILITY (the process gate): the supplier must be active, must
   have quoted this material category before (demonstrated capability),
   and must clear the technical-evaluation bar (avg TBE >= threshold) —
   the same TBE gate the company applies to real bids.
2. CRITERIA over the recorded history (per candidate):
     technical   avg TBE score on this category's quotations
     price       avg quoted total vs the per-RFQ median (ratio, lower=better)
     lead_time   avg quoted lead days on this category (lower=better)
     reliability historical on-time delivery rate, all shipments
     quality     goods-receipt QC acceptance rate
     terms       payment terms in days (longer=better for cash flow)
     ml_risk     the ACTIVE delivery-risk classifier scores a hypothetical
                 order for THIS need with THIS supplier (lower=better) —
                 the ML layer feeding the decision layer, context-aware.
3. NORMALIZE (min-max across candidates; cost criteria inverted), weight
   by the chosen profile, sum. The response carries raw value, normalized
   score, weight, and contribution for every criterion of every candidate:
   "the story behind the choice", as data.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings

logger = logging.getLogger("supplyscope.reco")

TBE_THRESHOLD = 70.0
COLD_START_QUOTES = 3

PRESETS: dict[str, dict[str, float]] = {
    "balanced":       {"technical": 0.15, "price": 0.20, "lead_time": 0.10,
                       "reliability": 0.20, "quality": 0.10, "terms": 0.05,
                       "ml_risk": 0.20},
    "cost_focused":   {"technical": 0.10, "price": 0.40, "lead_time": 0.05,
                       "reliability": 0.15, "quality": 0.10, "terms": 0.10,
                       "ml_risk": 0.10},
    "schedule_focused": {"technical": 0.10, "price": 0.10, "lead_time": 0.25,
                         "reliability": 0.25, "quality": 0.05, "terms": 0.00,
                         "ml_risk": 0.25},
}
# lower-is-better criteria get inverted during normalization
COST_CRITERIA = {"price", "lead_time", "ml_risk"}

_CANDIDATES_SQL = """
WITH rfq_cat AS (           -- each RFQ's dominant material category by value
    SELECT r.rfq_id,
           (SELECT m.category FROM erp.boq_lines bl
              JOIN erp.materials m USING (material_id)
             WHERE bl.boq_id = r.boq_id
             GROUP BY m.category
             ORDER BY sum(bl.quantity * m.ref_unit_price) DESC
             LIMIT 1) AS category
    FROM erp.rfqs r
),
cat_quotes AS (             -- this category's quotations, with per-RFQ median
    SELECT q.*, med.median_total
    FROM erp.supplier_quotations q
    JOIN rfq_cat rc USING (rfq_id)
    JOIN LATERAL (
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY q2.quoted_total)
               AS median_total
        FROM erp.supplier_quotations q2 WHERE q2.rfq_id = q.rfq_id
    ) med ON true
    WHERE rc.category = %(category)s
),
otd AS (                    -- reliability over ALL delivered shipments
    SELECT po.supplier_id,
           count(*) AS delivered,
           avg((s.actual_delivery_date <= po.promised_delivery_date)::int)
               AS otd_rate,
           avg((s.actual_delivery_date > po.promised_delivery_date)::int)
               AS prior_late_rate
    FROM erp.shipments s JOIN erp.purchase_orders po USING (po_id)
    WHERE s.actual_delivery_date IS NOT NULL
    GROUP BY po.supplier_id
),
quality AS (                -- QC acceptance over goods receipts
    SELECT po.supplier_id,
           avg((gr.qc_status = 'accepted')::int) AS accept_rate,
           count(*) AS receipts
    FROM erp.goods_receipts gr
    JOIN erp.shipments s USING (shipment_id)
    JOIN erp.purchase_orders po USING (po_id)
    GROUP BY po.supplier_id
)
SELECT sup.supplier_id, sup.supplier_code, sup.name, sup.country,
       sup.payment_terms_days,
       count(cq.quotation_id)                        AS n_quotes,
       round(avg(cq.tbe_score)::numeric, 1)                   AS avg_tbe,
       round(avg(cq.quoted_total / NULLIF(cq.median_total, 0))::numeric, 3)
                                                     AS price_ratio,
       round(avg(cq.lead_time_days)::numeric, 1)              AS avg_lead_days,
       o.delivered, round(o.otd_rate::numeric, 3)             AS otd_rate,
       round(o.prior_late_rate::numeric, 3)                   AS prior_late_rate,
       round(q.accept_rate::numeric, 3)                       AS qc_accept_rate,
       q.receipts
FROM erp.suppliers sup
JOIN cat_quotes cq ON cq.supplier_id = sup.supplier_id
LEFT JOIN otd o ON o.supplier_id = sup.supplier_id
LEFT JOIN quality q ON q.supplier_id = sup.supplier_id
WHERE sup.is_active
GROUP BY sup.supplier_id, o.delivered, o.otd_rate, o.prior_late_rate,
         q.accept_rate, q.receipts
HAVING avg(cq.tbe_score) >= %(tbe)s
ORDER BY sup.name
"""


def _ml_risk(candidates: list[dict], category: str,
             destination_country: str) -> dict[int, float] | None:
    """Score a hypothetical order per candidate with the ACTIVE classifier.
    Returns supplier_id -> p(late), or None when no model is trained."""
    try:
        import pandas as pd

        from app.ml import features as F
        from app.ml.registry import active_model, load_artifact
        row_model = active_model("delivery_risk")
        if row_model is None:
            return None
        pipe = load_artifact(row_model)
    except Exception:                                   # noqa: BLE001
        logger.exception("ml_risk unavailable")
        return None

    rows = []
    for c in candidates:
        is_import = c["country"] != destination_country
        rows.append({
            "transport_mode": "road" if c["country"] in ("Tunisie", "Libye")
                              else "sea",
            "incoterm": "DDP" if not is_import else "CIF",
            "supplier_country": c["country"],
            "destination_country": destination_country,
            "material_category": category,
            "promised_lead_days": int(c["avg_lead_days"] or 45),
            "amount_tnd": 250_000.0,
            "supplier_prior_shipments": int(c["delivered"] or 0),
            "supplier_prior_late_rate": float(
                c["prior_late_rate"] if c["prior_late_rate"] is not None
                else -1.0),
            "promised_month": 9,
            "requires_customs": is_import,
            "is_import": is_import,
        })
    X = pd.DataFrame(rows)[F.CATEGORICAL + F.NUMERIC + F.BOOLEAN]
    proba = pipe.predict_proba(X)[:, 1]
    return {c["supplier_id"]: round(float(p), 4)
            for c, p in zip(candidates, proba)}


def _minmax(values: dict[int, float | None], invert: bool) -> dict[int, float]:
    known = {k: v for k, v in values.items() if v is not None}
    if not known:
        return {k: 0.5 for k in values}
    lo, hi = min(known.values()), max(known.values())
    span = (hi - lo) or 1.0
    out = {}
    for k, v in values.items():
        if v is None:
            out[k] = 0.5                      # neutral when unknown
        else:
            n = (v - lo) / span
            out[k] = round(1.0 - n if invert else n, 4)
    return out


ALL_CRITERIA = ("technical", "price", "lead_time", "reliability",
                "quality", "terms", "ml_risk")


def normalize_weights(raw: dict[str, float]) -> dict[str, float]:
    """Validate a user-supplied weight vector and normalize it to sum 1.0.

    MCDA principle: weights are PREFERENCE parameters of the decision-maker,
    not facts of the world — so the system's job is not to impose them but
    to (a) accept any non-negative emphasis the user expresses, (b) reject
    only the meaningless (unknown criteria, negatives, all-zero), and
    (c) normalize so the explainability invariant — contributions sum to
    the score — holds for every possible slider position.
    """
    unknown = set(raw) - set(ALL_CRITERIA)
    if unknown:
        raise ValueError(f"Unknown criteria: {sorted(unknown)}; "
                         f"valid: {list(ALL_CRITERIA)}")
    if any(v < 0 for v in raw.values()):
        raise ValueError("Weights must be non-negative")
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("At least one weight must be positive")
    return {k: v / total for k, v in raw.items() if v > 0}


def recommend(category: str, destination_country: str = "Tunisie",
              preset: str = "balanced", top_n: int = 5,
              custom_weights: dict[str, float] | None = None
              ) -> dict[str, Any]:
    if custom_weights is not None:
        weights = normalize_weights(custom_weights)
        preset = "custom"
    else:
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset '{preset}'")
        weights = PRESETS[preset]
    with psycopg.connect(get_settings().app_dsn, row_factory=dict_row) as conn:
        cands = conn.execute(_CANDIDATES_SQL,
                             {"category": category, "tbe": TBE_THRESHOLD}
                             ).fetchall()
    if not cands:
        return {"category": category, "preset": preset, "candidates": [],
                "note": "No supplier has a TBE-qualified quotation history "
                        "for this category."}

    risk = _ml_risk(cands, category, destination_country)
    raw: dict[str, dict[int, float | None]] = {
        "technical": {c["supplier_id"]: float(c["avg_tbe"]) for c in cands},
        "price": {c["supplier_id"]: float(c["price_ratio"]) for c in cands},
        "lead_time": {c["supplier_id"]: float(c["avg_lead_days"]) for c in cands},
        "reliability": {c["supplier_id"]:
                        None if c["otd_rate"] is None else float(c["otd_rate"])
                        for c in cands},
        "quality": {c["supplier_id"]:
                    None if c["qc_accept_rate"] is None
                    else float(c["qc_accept_rate"]) for c in cands},
        "terms": {c["supplier_id"]: float(c["payment_terms_days"])
                  for c in cands},
    }
    if risk is not None:
        raw["ml_risk"] = {c["supplier_id"]: risk[c["supplier_id"]]
                          for c in cands}
    active_weights = {k: w for k, w in weights.items() if k in raw}
    wsum = sum(active_weights.values()) or 1.0
    active_weights = {k: w / wsum for k, w in active_weights.items()}

    norm = {k: _minmax(v, invert=(k in COST_CRITERIA)) for k, v in raw.items()}

    results = []
    for c in cands:
        sid = c["supplier_id"]
        breakdown = []
        total = 0.0
        for crit, w in active_weights.items():
            contrib = round(norm[crit][sid] * w, 4)
            total += contrib
            breakdown.append({
                "criterion": crit, "weight": round(w, 3),
                "raw": raw[crit][sid], "normalized": norm[crit][sid],
                "contribution": contrib,
                "direction": "lower is better" if crit in COST_CRITERIA
                             else "higher is better",
            })
        results.append({
            "supplier_id": sid, "supplier_code": c["supplier_code"],
            "name": c["name"], "country": c["country"],
            "score": round(total, 4),
            "cold_start": c["n_quotes"] < COLD_START_QUOTES,
            "evidence": {"category_quotes": c["n_quotes"],
                         "delivered_shipments": c["delivered"] or 0,
                         "qc_receipts": c["receipts"] or 0},
            "breakdown": sorted(breakdown, key=lambda b: -b["contribution"]),
        })
    results.sort(key=lambda r: -r["score"])
    return {"category": category, "destination_country": destination_country,
            "preset": preset, "weights": active_weights,
            "method": "Simple Additive Weighting (min-max normalized)",
            "ml_risk_included": risk is not None,
            "eligibility": {"tbe_threshold": TBE_THRESHOLD,
                            "capability": "has quoted this category",
                            "active_only": True},
            "candidates": results[:top_n]}
