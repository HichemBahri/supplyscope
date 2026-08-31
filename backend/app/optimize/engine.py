"""Procurement award optimization (Phase 12) — Mixed-Integer Linear
Programming over the genuinely open RFQs in the world.

Where the recommender RANKS candidates for one need, the optimizer
ALLOCATES awards across all open needs AT ONCE, under constraints that
couple them (shared budget, supplier concentration). Different question,
different mathematics: this is operations research, solved exactly.

    minimize   Σ  x[r,s] · ( price_tnd[r,s] + p_late[r,s] · λ · price_tnd[r,s] )
    subject to Σ_s x[r,s] = 1                        for every open RFQ r
               Σ_{r,s} x[r,s] · price_tnd[r,s] ≤ B   (budget, optional)
               awarded_value[s] ≤ γ · total_awarded  for every supplier s
               x[r,s] ∈ {0,1}

- price_tnd:  the supplier's ACTUAL quoted total, FX-normalized — real bids,
  not estimates.
- p_late:     the ACTIVE delivery-risk classifier scoring THIS candidate
  order (supplier country/history × category × destination) — the ML layer
  pricing risk inside the objective.
- λ (penalty_rate): expected extra cost of a late award as a fraction of
  order value (default 0.15) — a documented, tunable business assumption.
- γ (max_supplier_share): the 40% concentration ceiling, imported from the
  expert-system rule SUPPLIER_CONCENTRATION — the rule layer becoming a
  constraint.

Solver: PuLP + CBC (open-source, deterministic). The response reports the
solve status, the allocation with per-award reasoning, binding constraints,
and the comparison against the naive cheapest-bid baseline.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import psycopg
import pulp
from psycopg.rows import dict_row

from app.config import get_settings
from app.expert.rules import CONCENTRATION_THRESHOLD

logger = logging.getLogger("supplyscope.optimize")

DEFAULT_PENALTY_RATE = 0.15

_BIDS_SQL = """
WITH rfq_cat AS (
    SELECT r.rfq_id,
           (SELECT m.category FROM erp.boq_lines bl
              JOIN erp.materials m USING (material_id)
             WHERE bl.boq_id = r.boq_id
             GROUP BY m.category
             ORDER BY sum(bl.quantity * m.ref_unit_price) DESC
             LIMIT 1) AS category
    FROM erp.rfqs r
),
sup_hist AS (
    SELECT po.supplier_id,
           count(*) AS delivered,
           avg((s.actual_delivery_date > po.promised_delivery_date)::int)
               AS prior_late_rate
    FROM erp.shipments s JOIN erp.purchase_orders po USING (po_id)
    WHERE s.actual_delivery_date IS NOT NULL
    GROUP BY po.supplier_id
)
SELECT r.rfq_id, r.rfq_ref, rc.category,
       p.project_code, st.country AS destination_country,
       q.quotation_id, q.quoted_total, q.currency, q.lead_time_days,
       q.tbe_score,
       fx.rate_to_tnd,
       (q.quoted_total * fx.rate_to_tnd) AS price_tnd,
       sup.supplier_id, sup.supplier_code, sup.name AS supplier_name,
       sup.country AS supplier_country,
       coalesce(h.delivered, 0) AS prior_shipments,
       h.prior_late_rate
FROM erp.rfqs r
JOIN rfq_cat rc USING (rfq_id)
JOIN erp.boqs b USING (boq_id)
JOIN erp.projects p USING (project_id)
JOIN erp.sites st ON st.site_id = p.site_id
JOIN erp.supplier_quotations q USING (rfq_id)
JOIN erp.fx_rates fx ON fx.currency = q.currency
JOIN erp.suppliers sup ON sup.supplier_id = q.supplier_id
LEFT JOIN sup_hist h ON h.supplier_id = sup.supplier_id
WHERE EXISTS (SELECT 1 FROM erp.purchase_orders po
              WHERE po.rfq_id = r.rfq_id
                AND po.order_date >= %(since)s)
  AND sup.is_active
  AND q.tbe_score >= 70
ORDER BY r.rfq_id, q.quoted_total
"""

_ACTUAL_SQL = """
SELECT po.rfq_id, q.quotation_id
FROM erp.purchase_orders po
JOIN erp.supplier_quotations q
  ON q.rfq_id = po.rfq_id AND q.supplier_id = po.supplier_id
WHERE po.rfq_id IS NOT NULL AND po.order_date >= %(since)s
"""


def _p_late(bids: list[dict]) -> dict[int, float]:
    """Score every candidate (rfq, supplier) pair with the active
    classifier; neutral 0.5 when no model is available."""
    try:
        import pandas as pd

        from app.ml import features as F
        from app.ml.registry import active_model, load_artifact
        row = active_model("delivery_risk")
        if row is None:
            return {b["quotation_id"]: 0.5 for b in bids}
        pipe = load_artifact(row)
    except Exception:                                   # noqa: BLE001
        logger.exception("optimizer: classifier unavailable, neutral risk")
        return {b["quotation_id"]: 0.5 for b in bids}

    rows = []
    for b in bids:
        is_import = b["supplier_country"] != b["destination_country"]
        rows.append({
            "transport_mode": "road"
                if b["supplier_country"] in ("Tunisie", "Libye") else "sea",
            "incoterm": "CIF" if is_import else "DDP",
            "supplier_country": b["supplier_country"],
            "destination_country": b["destination_country"],
            "material_category": b["category"],
            "promised_lead_days": int(b["lead_time_days"] or 45),
            "amount_tnd": float(b["price_tnd"]),
            "supplier_prior_shipments": int(b["prior_shipments"]),
            "supplier_prior_late_rate": float(
                b["prior_late_rate"] if b["prior_late_rate"] is not None
                else -1.0),
            "promised_month": 9,
            "requires_customs": is_import,
            "is_import": is_import,
        })
    X = pd.DataFrame(rows)[F.CATEGORICAL + F.NUMERIC + F.BOOLEAN]
    proba = pipe.predict_proba(X)[:, 1]
    return {b["quotation_id"]: round(float(p), 4)
            for b, p in zip(bids, proba)}


def optimize_awards(budget_tnd: float | None = None,
                    penalty_rate: float = DEFAULT_PENALTY_RATE,
                    max_supplier_share: float = CONCENTRATION_THRESHOLD,
                    risk_ceiling: float = 0.65,
                    since: str = "2026-01-01",
                    ) -> dict[str, Any]:
    """Retrospective what-if: re-optimize the awards of RFQs decided since
    `since`, choosing among the ACTUAL bids received (winners and losers,
    TBE-qualified), and compare against the company's actual allocation."""
    with psycopg.connect(get_settings().app_dsn, row_factory=dict_row) as c:
        bids = c.execute(_BIDS_SQL, {"since": since}).fetchall()
        actual_rows = c.execute(_ACTUAL_SQL, {"since": since}).fetchall()
    if not bids:
        return {"status": "no_rfqs_in_window", "allocations": []}
    actual_q = {r["rfq_id"]: r["quotation_id"] for r in actual_rows}
    for b in bids:
        b["price_tnd"] = float(b["price_tnd"])
    risk = _p_late(bids)
    for b in bids:
        b["p_late"] = risk[b["quotation_id"]]
        b["expected_cost"] = round(
            b["price_tnd"] * (1.0 + penalty_rate * b["p_late"]), 2)

    have_actual = {b["rfq_id"] for b in bids
                   if actual_q.get(b["rfq_id"]) == b["quotation_id"]}
    bids = [b for b in bids if b["rfq_id"] in have_actual]
    multi = {r for r in have_actual
             if sum(1 for b in bids if b["rfq_id"] == r) >= 2}
    bids = [b for b in bids if b["rfq_id"] in multi]
    if not bids:
        return {"status": "no_contested_rfqs", "allocations": []}
    rfqs = sorted({b["rfq_id"] for b in bids})
    suppliers = sorted({b["supplier_id"] for b in bids})
    by_rfq: dict[int, list[dict]] = {r: [] for r in rfqs}
    for b in bids:
        by_rfq[b["rfq_id"]].append(b)

    # --- the MILP ---
    prob = pulp.LpProblem("procurement_awards", pulp.LpMinimize)
    x = {b["quotation_id"]: pulp.LpVariable(f"x_{b['quotation_id']}",
                                            cat="Binary") for b in bids}
    prob += pulp.lpSum(x[b["quotation_id"]] * b["expected_cost"]
                       for b in bids), "expected_total_cost"
    for r in rfqs:                                  # exactly one award each
        prob += (pulp.lpSum(x[b["quotation_id"]] for b in by_rfq[r]) == 1,
                 f"award_rfq_{r}")
    # risk ceiling: exclude any bid above the threshold *provided* the RFQ
    # still has at least one compliant bid — never make an RFQ unfillable
    risk_excluded = 0
    for r in rfqs:
        compliant = [b for b in by_rfq[r] if b["p_late"] <= risk_ceiling]
        if compliant:                               # only enforce if feasible
            for b in by_rfq[r]:
                if b["p_late"] > risk_ceiling:
                    prob += (x[b["quotation_id"]] == 0,
                             f"risk_ceiling_{b['quotation_id']}")
                    risk_excluded += 1
    if budget_tnd is not None:                      # budget on cash spend
        prob += (pulp.lpSum(x[b["quotation_id"]] * b["price_tnd"]
                            for b in bids) <= budget_tnd, "budget")
    total_awarded = pulp.lpSum(x[b["quotation_id"]] * b["price_tnd"]
                               for b in bids)
    for s in suppliers:                             # concentration ceiling
        s_val = pulp.lpSum(x[b["quotation_id"]] * b["price_tnd"]
                           for b in bids if b["supplier_id"] == s)
        prob += (s_val <= max_supplier_share * total_awarded,
                 f"concentration_{s}")

    t0 = time.perf_counter()
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[prob.status]
    concentration_mode = "hard"
    if status != "Optimal":
        # lumpy indivisible awards can make the ceiling arithmetically
        # impossible; keep it as an ADVISORY and report the breach honestly
        for s in suppliers:
            del prob.constraints[f"concentration_{s}"]
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        status = pulp.LpStatus[prob.status]
        concentration_mode = "advisory (infeasible as hard constraint)"
    ms = round((time.perf_counter() - t0) * 1000, 1)
    if status != "Optimal":
        return {"status": status, "solver_ms": ms, "allocations": [],
                "note": "No feasible allocation under these constraints "
                        "(try raising the budget)."}

    chosen = [b for b in bids if x[b["quotation_id"]].value() == 1]
    baseline = [min(by_rfq[r], key=lambda b: b["price_tnd"]) for r in rfqs]
    actual = [next(b for b in by_rfq[r]
                   if b["quotation_id"] == actual_q[r]) for r in rfqs]

    def _tot(sel):
        price = sum(b["price_tnd"] for b in sel)
        pen = sum(b["price_tnd"] * penalty_rate * b["p_late"] for b in sel)
        return {"price_tnd": round(price, 2),
                "expected_penalty_tnd": round(pen, 2),
                "expected_total_tnd": round(price + pen, 2),
                "avg_p_late": round(sum(b["p_late"] for b in sel) / len(sel), 4),
                "avg_lead_days": round(sum(float(b["lead_time_days"] or 0)
                                           for b in sel) / len(sel), 1)}

    tot, base, act = _tot(chosen), _tot(baseline), _tot(actual)
    # "cheapest by price" ignores the risk ceiling — it's the naive policy
    # the optimizer improves upon in EXPECTED terms
    shares = {}
    for b in chosen:
        shares[b["supplier_code"]] = shares.get(b["supplier_code"], 0.0) \
            + b["price_tnd"]
    max_share = max(v / tot["price_tnd"] for v in shares.values())

    return {
        "status": status, "solver_ms": ms,
        "method": "Mixed-Integer Linear Programming (PuLP + CBC)",
        "parameters": {"budget_tnd": budget_tnd,
                       "penalty_rate": penalty_rate,
                       "max_supplier_share": max_supplier_share,
                       "risk_ceiling": risk_ceiling},
        "open_rfqs": len(rfqs), "candidate_bids": len(bids),
        "allocations": [{
            "rfq_ref": b["rfq_ref"], "category": b["category"],
            "project": b["project_code"],
            "destination": b["destination_country"],
            "supplier_code": b["supplier_code"],
            "supplier_name": b["supplier_name"],
            "price_tnd": round(b["price_tnd"], 2),
            "p_late": b["p_late"],
            "expected_cost_tnd": b["expected_cost"],
            "was_cheapest_bid": b is min(by_rfq[b["rfq_id"]],
                                         key=lambda q: q["price_tnd"]),
            "was_actual_award": b["quotation_id"] == actual_q[b["rfq_id"]],
            "bids_considered": len(by_rfq[b["rfq_id"]]),
        } for b in sorted(chosen, key=lambda q: q["rfq_ref"])],
        "totals": tot,
        "actual_allocation": act,
        "baseline_cheapest": base,
        "savings_vs_actual_tnd": round(act["expected_total_tnd"]
                                       - tot["expected_total_tnd"], 2),
        "savings_vs_actual_pct": round(
            100.0 * (act["expected_total_tnd"] - tot["expected_total_tnd"])
            / act["expected_total_tnd"], 2) if act["expected_total_tnd"]
            else 0.0,
        "savings_vs_cheapest_tnd": round(base["expected_total_tnd"]
                                         - tot["expected_total_tnd"], 2),
        "constraints_report": {
            "budget_binding": budget_tnd is not None and
                abs(tot["price_tnd"] - budget_tnd) < 1.0,
            "max_supplier_share_actual": round(max_share, 3),
            "concentration_ceiling": max_supplier_share,
            "concentration_mode": concentration_mode,
            "risk_ceiling": risk_ceiling,
            "bids_excluded_by_risk": risk_excluded,
            "diverged_from_cheapest": sum(
                1 for b in chosen if b is not min(
                    by_rfq[b["rfq_id"]], key=lambda q: q["price_tnd"])),
        },
    }


if __name__ == "__main__":
    import json
    out = optimize_awards()  # retrospective window since 2026-01-01
    print(json.dumps({k: v for k, v in out.items() if k != "allocations"},
                     indent=2, default=str))
    for a in out.get("allocations", []):
        star = "*" if not a["was_actual_award"] else " "
        print(f"  {star} {a['rfq_ref']:14s} {a['category']:16s} "
              f"-> {a['supplier_name']:30s} {a['price_tnd']:>12,.0f} TND  "
              f"p_late={a['p_late']:.3f}")
