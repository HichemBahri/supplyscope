"""Phase 15b/c — the deterministic evaluations must be internally
consistent: the sweep's monotone quantities are monotone, the frontier is
a real frontier, the actual allocation is dominated by it, and the
ablation covers the ML criterion with sane statistics."""
from __future__ import annotations

from scripts.eval_optimizer import pareto, sweep
from scripts.eval_recommender import ablate, summarize


def test_sweep_monotone_and_frontier(tmp_path):
    rows = sweep(lambdas=(0.15,), ceilings=(0.30, 0.45, 0.60, 0.75, 0.90))
    assert len(rows) == 5
    above = [r["bids_above_ceiling"] for r in rows]
    assert above == sorted(above, reverse=True)          # loosening never adds risky bids
    waived = [r["rfqs_waived"] for r in rows]
    assert waived == sorted(waived, reverse=True) and waived[-1] == 0
    assert rows[-1]["diverged_from_cheapest"] == 0       # ceiling 0.90: collapses to cheapest
    front = pareto(rows)
    assert front
    prices = [p["price_tnd"] for p in front]
    assert prices == sorted(prices, reverse=True)        # cheaper as risk rises
    # the company's actual allocation is dominated by the frontier
    ref = rows[0]
    assert any(p["price_tnd"] <= ref["actual_price_tnd"] and
               p["avg_p_late"] <= ref["actual_avg_p_late"] for p in front)


def test_ablation_covers_ml_and_is_sane():
    rows = ablate()
    assert rows and any(r["removed"] == "ml_risk" for r in rows)
    for r in rows:
        assert 0 <= r["top3_overlap"] <= 1
        assert r["spearman"] is None or -1 <= r["spearman"] <= 1
        assert r["winner_changed"] == int(r["winner_full"] != r["winner_ablated"])
    # zero-weight criteria are never "removed" (schedule_focused has terms=0)
    assert not any(r["preset"] == "schedule_focused" and r["removed"] == "terms" for r in rows)
    s = summarize(rows)
    assert 0 <= s["ml_risk"]["winner_change_rate"] <= 100
    assert len(s["ml_risk"]["changed_cases"]) == round(
        s["ml_risk"]["winner_change_rate"] * s["ml_risk"]["cases"] / 100)
