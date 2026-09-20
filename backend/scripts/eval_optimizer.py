"""Optimizer sensitivity sweep (Phase 15b) — the efficient frontier.

Re-solves the award MILP over a grid of the two policy levers — the delay
penalty λ and the risk ceiling — and records, for every point, the cash
cost, the expected cost, the average predicted lateness of the chosen
allocation, and the constraint accounting. Two figures come out:

  1. The EFFICIENT FRONTIER: cash price vs average p(late). Each point is
     one policy setting; the Pareto-optimal ones are joined. The company's
     ACTUAL awards and the naive cheapest allocation are plotted as
     reference marks — the frontier shows what the optimizer can buy that
     neither reference could.
  2. The CEILING ANATOMY: bids above the ceiling (monotone), RFQs where the
     policy is enforced vs waived, and the resulting "forbidden" count —
     the figure that explains why "excluded" is not monotone.

No LLM, deterministic, ~65 solves of ~30 ms each.

Usage:  python -m scripts.eval_optimizer [--out bench_results]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from app.optimize.engine import optimize_awards

NAVY, ACTION, MUTED, WARN, DANGER = "#0B2239", "#155E97", "#94A3B8", "#b97d10", "#B23A48"

LAMBDAS = (0.0, 0.15, 0.30, 0.50, 1.00)
CEILINGS = tuple(round(0.30 + 0.05 * i, 2) for i in range(13))     # 0.30 … 0.90


def sweep(lambdas: tuple[float, ...] = LAMBDAS,
          ceilings: tuple[float, ...] = CEILINGS) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lam in lambdas:
        for c in ceilings:
            o = optimize_awards(penalty_rate=lam, risk_ceiling=c)
            if o["status"] != "Optimal":
                continue
            r = o["constraints_report"]
            rows.append({
                "penalty_rate": lam, "risk_ceiling": c,
                "price_tnd": o["totals"]["price_tnd"],
                "expected_total_tnd": o["totals"]["expected_total_tnd"],
                "avg_p_late": o["totals"]["avg_p_late"],
                "avg_lead_days": o["totals"]["avg_lead_days"],
                "bids_above_ceiling": r["bids_above_ceiling"],
                "rfqs_enforced": r["rfqs_ceiling_enforced"],
                "rfqs_waived": r["rfqs_ceiling_waived"],
                "bids_forbidden": r["bids_excluded_by_risk"],
                "diverged_from_cheapest": r["diverged_from_cheapest"],
                "max_supplier_share": r["max_supplier_share_actual"],
                "solver_ms": o["solver_ms"],
                # references (identical for every point; kept for the CSV)
                "actual_price_tnd": o["actual_allocation"]["price_tnd"],
                "actual_avg_p_late": o["actual_allocation"]["avg_p_late"],
                "cheapest_price_tnd": o["baseline_cheapest"]["price_tnd"],
                "cheapest_avg_p_late": o["baseline_cheapest"]["avg_p_late"],
            })
    return rows


_DIVERGENCE_SQL = """
WITH bids AS (
  SELECT r.rfq_id, r.rfq_ref, q.quotation_id, q.supplier_id, q.quoted_total AS nominal,
         q.currency, q.quoted_total*f.rate_to_tnd AS tnd
  FROM erp.rfqs r JOIN erp.supplier_quotations q USING (rfq_id)
  JOIN erp.fx_rates f ON f.currency=q.currency
  JOIN erp.suppliers s ON s.supplier_id=q.supplier_id
  WHERE s.is_active AND q.tbe_score>=70
    AND EXISTS (SELECT 1 FROM erp.purchase_orders po
                WHERE po.rfq_id=r.rfq_id AND po.order_date>=%(since)s)),
actual AS (SELECT b.* FROM bids b JOIN erp.purchase_orders po
           ON po.rfq_id=b.rfq_id AND po.supplier_id=b.supplier_id
           WHERE po.order_date>=%(since)s),
cheapest AS (SELECT DISTINCT ON (rfq_id) * FROM bids ORDER BY rfq_id, tnd)
SELECT a.rfq_ref, a.currency AS actual_ccy, a.nominal AS actual_nominal, a.tnd AS actual_tnd,
       c.currency AS cheapest_ccy, c.nominal AS cheapest_nominal, c.tnd AS cheapest_tnd,
       a.tnd - c.tnd AS overpaid_tnd,
       (a.nominal < c.nominal AND a.currency <> c.currency) AS nominal_illusion
FROM actual a JOIN cheapest c USING (rfq_id)
WHERE a.quotation_id <> c.quotation_id
  AND (SELECT count(*) FROM bids b2 WHERE b2.rfq_id=a.rfq_id) >= 2
ORDER BY overpaid_tnd DESC
"""


def divergence_audit(since: str = "2026-01-01") -> list[dict[str, Any]]:
    """The actual awards that differ from the cheapest bid, with the reason.
    `nominal_illusion` flags the simulator's known flaw: it compared quoted
    totals across currencies without converting, so a USD bid with a
    smaller NUMBER won over a cheaper TND bid. Those divergences are an
    artifact of the synthetic world, not evidence of optimizer superiority
    over real buyers — who do convert currencies."""
    import psycopg
    from psycopg.rows import dict_row

    from app.config import get_settings
    with psycopg.connect(get_settings().app_dsn, row_factory=dict_row) as c:
        rows = c.execute(_DIVERGENCE_SQL, {"since": since}).fetchall()
    return [{k: (float(v) if hasattr(v, "quantize") else v) for k, v in r.items()}
            for r in rows]


def pareto(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Points not dominated on (lower price, lower risk)."""
    pts = sorted({(r["avg_p_late"], r["price_tnd"]) for r in rows})
    front, best_price = [], float("inf")
    for risk, price in pts:                     # ascending risk
        if price < best_price:                  # strictly cheaper than all lower-risk points
            front.append({"avg_p_late": risk, "price_tnd": price})
            best_price = price
    return front


def write(rows: list[dict[str, Any]], out: Path, with_actual: bool = False) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "optimizer_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    front = pareto(rows)
    ref = rows[0]
    lo = min(rows, key=lambda r: r["avg_p_late"])
    hi = min(rows, key=lambda r: r["price_tnd"])
    md = [
        "# Optimizer sensitivity sweep", "",
        f"{len(rows)} policy settings solved (λ ∈ {list(LAMBDAS)}, ceiling ∈ "
        f"[{CEILINGS[0]}, {CEILINGS[-1]}]); {len(front)} on the efficient frontier.", "",
        "| reference | cash price (TND) | avg p(late) |", "|---|---|---|",
        f"| actual awards | {ref['actual_price_tnd']:,.0f} | {ref['actual_avg_p_late']:.3f} |",
        f"| naive cheapest | {ref['cheapest_price_tnd']:,.0f} | {ref['cheapest_avg_p_late']:.3f} |",
        f"| cheapest policy point | {hi['price_tnd']:,.0f} | {hi['avg_p_late']:.3f} "
        f"(λ={hi['penalty_rate']}, ceiling {hi['risk_ceiling']}) |",
        f"| lowest-risk policy point | {lo['price_tnd']:,.0f} | {lo['avg_p_late']:.3f} "
        f"(λ={lo['penalty_rate']}, ceiling {lo['risk_ceiling']}) |", "",
        f"Risk reduction available: {ref['cheapest_avg_p_late']:.3f} → {lo['avg_p_late']:.3f} "
        f"avg p(late) for +{lo['price_tnd'] - hi['price_tnd']:,.0f} TND "
        f"(+{100 * (lo['price_tnd'] / hi['price_tnd'] - 1):.1f}% cash).", "",
        "## Why the 'actual awards' reference is NOT a savings claim", "",
        "Actual awards that differ from the cheapest FX-normalized bid, and why:", "",
        "| RFQ | actual bid | cheapest bid | overpaid (TND) | nominal-currency illusion |",
        "|---|---|---|---|---|",
    ]
    audit = divergence_audit()
    art = sum(r["overpaid_tnd"] for r in audit if r["nominal_illusion"])
    tot = sum(r["overpaid_tnd"] for r in audit)
    for r in audit:
        md.append(f"| {r['rfq_ref']} | {r['actual_ccy']} {r['actual_nominal']:,.0f} "
                  f"(= {r['actual_tnd']:,.0f} TND) | {r['cheapest_ccy']} {r['cheapest_nominal']:,.0f} "
                  f"(= {r['cheapest_tnd']:,.0f} TND) | {r['overpaid_tnd']:,.0f} | "
                  f"{'yes' if r['nominal_illusion'] else 'no'} |")
    md += ["",
        f"{sum(r['nominal_illusion'] for r in audit)} of {len(audit)} divergent awards are the "
        f"simulator's nominal-currency comparison flaw; they account for {art:,.0f} of the "
        f"{tot:,.0f} TND gap ({100 * art / tot:.1f}%). The optimizer 'beats' the simulated "
        "history mainly by converting currencies — which real buyers also do. The frontier "
        "itself (all points FX-normalized) is unaffected; only the actual-vs-optimizer "
        "distance is an artifact.", "",
        "## Ceiling anatomy (λ = 0.15)", "",
        "| ceiling | above | enforced | waived | forbidden | diverged | avg p(late) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["penalty_rate"] == 0.15:
            md.append(f"| {r['risk_ceiling']:.2f} | {r['bids_above_ceiling']} | {r['rfqs_enforced']} "
                      f"| {r['rfqs_waived']} | {r['bids_forbidden']} | {r['diverged_from_cheapest']} "
                      f"| {r['avg_p_late']:.3f} |")
    (out / "optimizer_sweep.md").write_text("\n".join(md) + "\n")
    _plot(rows, front, out, with_actual=with_actual)
    return {"points": len(rows), "frontier": front, "lowest_risk": lo, "cheapest": hi,
            "divergence_audit": audit}


def _plot(rows: list[dict[str, Any]], front: list[dict[str, Any]], out: Path,
          with_actual: bool = False) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ref = rows[0]
    # ---- figure 1: efficient frontier ----
    fig, ax = plt.subplots(figsize=(8, 5))
    shades = {0.0: "#9DB4CC", 0.15: "#6C8FB5", 0.30: "#3F6C9E", 0.50: "#1F4E85", 1.00: NAVY}
    for lam in LAMBDAS:
        pts = [r for r in rows if r["penalty_rate"] == lam]
        ax.scatter([p["avg_p_late"] for p in pts], [p["price_tnd"] / 1e6 for p in pts],
                   s=34, color=shades[lam], edgecolor="white", linewidth=0.8,
                   label=f"λ = {lam:.2f}", zorder=3)
    ax.plot([p["avg_p_late"] for p in front], [p["price_tnd"] / 1e6 for p in front],
            color=ACTION, linewidth=2, zorder=2, label="efficient frontier")
    if with_actual:      # off by default: that distance is a simulator artifact (see .md)
        ax.scatter([ref["actual_avg_p_late"]], [ref["actual_price_tnd"] / 1e6], marker="X",
                   s=140, color=DANGER, zorder=4, label="simulated historical awards")
        ax.annotate("simulated history", (ref["actual_avg_p_late"], ref["actual_price_tnd"] / 1e6),
                    xytext=(-95, 6), textcoords="offset points", color=DANGER, fontsize=9)
    ax.scatter([ref["cheapest_avg_p_late"]], [ref["cheapest_price_tnd"] / 1e6], marker="D",
               s=90, color=WARN, zorder=4, label="naive cheapest")
    ax.annotate("cheapest", (ref["cheapest_avg_p_late"], ref["cheapest_price_tnd"] / 1e6),
                xytext=(8, -12), textcoords="offset points", color=WARN, fontsize=9)
    ax.set_xlabel("average predicted p(late) of the allocation")
    ax.set_ylabel("cash price of the allocation (M TND)")
    ax.set_title("Award optimizer — the cost of risk reduction (65 policy settings, all FX-normalized)",
                 loc="left", fontsize=11)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout(); fig.savefig(out / "optimizer_frontier.png", dpi=150); plt.close(fig)

    # ---- figure 2: ceiling anatomy at λ = 0.15 ----
    pts = [r for r in rows if r["penalty_rate"] == 0.15]
    xs = [r["risk_ceiling"] for r in pts]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(xs, [r["bids_above_ceiling"] for r in pts], "o-", color=NAVY, linewidth=2,
            markersize=5, label="bids above ceiling (monotone)")
    ax.plot(xs, [r["bids_forbidden"] for r in pts], "s-", color=ACTION, linewidth=2,
            markersize=5, label="bids forbidden (policy enforced only)")
    ax.plot(xs, [r["rfqs_waived"] for r in pts], "^-", color=WARN, linewidth=2,
            markersize=5, label="RFQs with no compliant bid (policy waived)")
    ax.set_xlabel("risk ceiling  p(late) ≤")
    ax.set_ylabel("count")
    ax.set_title("Why 'forbidden' is not monotone: the waiver switches policy on/off per RFQ",
                 loc="left", fontsize=11)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout(); fig.savefig(out / "optimizer_ceiling_anatomy.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench_results")
    ap.add_argument("--with-actual", action="store_true",
                    help="also plot the simulated historical awards (artifact-inflated)")
    a = ap.parse_args()
    rows = sweep()
    s = write(rows, Path(a.out), with_actual=a.with_actual)
    aud = s["divergence_audit"]
    print(f"divergence audit: {sum(r['nominal_illusion'] for r in aud)}/{len(aud)} actual-vs-cheapest "
          f"gaps are the simulator's nominal-currency flaw")
    print(f"{s['points']} settings solved; frontier has {len(s['frontier'])} points")
    print(f"cheapest policy: {s['cheapest']['price_tnd']:,.0f} TND @ p_late {s['cheapest']['avg_p_late']:.3f}")
    print(f"lowest-risk policy: {s['lowest_risk']['price_tnd']:,.0f} TND @ p_late {s['lowest_risk']['avg_p_late']:.3f}")
    print(f"reports: {Path(a.out)}/optimizer_sweep.{{csv,md}}, optimizer_frontier.png, optimizer_ceiling_anatomy.png")
