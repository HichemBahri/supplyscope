"""Phase 12 — award optimization: exact solve, constraint integrity,
honest comparison against actual awards."""
from __future__ import annotations

from app.optimize.engine import optimize_awards


def test_solves_optimally_with_hard_concentration():
    out = optimize_awards()
    assert out["status"] == "Optimal"
    assert out["open_rfqs"] >= 20 and out["candidate_bids"] > out["open_rfqs"]
    r = out["constraints_report"]
    assert r["concentration_mode"] == "hard"
    assert r["max_supplier_share_actual"] <= r["concentration_ceiling"] + 1e-6


def test_one_award_per_rfq_and_decomposition():
    out = optimize_awards()
    refs = [a["rfq_ref"] for a in out["allocations"]]
    assert len(refs) == len(set(refs)) == out["open_rfqs"]
    t = out["totals"]
    assert abs(t["price_tnd"] + t["expected_penalty_tnd"]
               - t["expected_total_tnd"]) < 1.0


def test_beats_actual_in_expected_terms():
    out = optimize_awards()
    assert out["totals"]["expected_total_tnd"] <= \
        out["actual_allocation"]["expected_total_tnd"] + 1.0
    assert out["savings_vs_actual_tnd"] >= 0


def test_risk_ceiling_binds_and_forces_divergence():
    """At a tight ceiling the optimizer must exclude risky bids and pick a
    non-cheapest supplier on at least one RFQ — proof the ML risk model is
    load-bearing, not decorative."""
    out = optimize_awards(risk_ceiling=0.65)
    r = out["constraints_report"]
    assert r["bids_excluded_by_risk"] > 0
    assert r["diverged_from_cheapest"] > 0
    # the chosen allocation's average risk is below the naive cheapest's
    assert out["totals"]["avg_p_late"] <= \
        out["baseline_cheapest"]["avg_p_late"] + 1e-9


def test_loose_ceiling_reduces_to_cheapest():
    """With the ceiling disabled (0.9) and tiny penalty, the optimum is the
    cheapest-bid allocation — a sanity anchor."""
    out = optimize_awards(risk_ceiling=0.90, penalty_rate=0.15)
    assert out["constraints_report"]["diverged_from_cheapest"] == 0


def test_majority_of_actual_awards_confirmed():
    """The tool reviews, it does not overturn: most recorded awards were
    already optimal; savings concentrate in a few flagged RFQs."""
    out = optimize_awards()
    kept = sum(1 for a in out["allocations"] if a["was_actual_award"])
    assert kept >= out["open_rfqs"] * 0.5


def test_tight_budget_reported_infeasible():
    out = optimize_awards(budget_tnd=1000.0)
    assert out["status"] != "Optimal" and out["allocations"] == []
