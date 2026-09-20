"""Recommender ablation (Phase 15c) — how much does each criterion matter?

For every material category × weight preset, the SAW ranking is computed
with the full weight vector and then with ONE criterion removed (its
weight set to zero, the rest renormalized). Three effects are measured
per removed criterion:

  winner-change rate   share of (category, preset) cases whose #1 changes
  top-3 overlap        mean |top3_full ∩ top3_ablated| / 3
  rank correlation     mean Spearman ρ between the two full rankings

The ML-risk criterion is the one the thesis cares about: it is the
classifier feeding forward into the decision layer, and this is the
experiment that puts a number on its influence. But ablating EVERY
criterion also yields a criterion-influence profile — which weights
actually move decisions in this world.

No LLM, deterministic.

Usage:  python -m scripts.eval_recommender [--out bench_results]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from app.reco.engine import ALL_CRITERIA, PRESETS, recommend

NAVY, ACTION, MUTED = "#0B2239", "#155E97", "#94A3B8"
CATEGORIES = ("steel", "electrical", "instrumentation", "safety", "piping",
              "valves", "mechanical_equipment", "welding_consumables")


def _ranking(category: str, preset: str, weights: dict[str, float] | None) -> list[str]:
    out = (recommend(category, preset=preset, top_n=10) if weights is None
           else recommend(category, top_n=10, custom_weights=weights))
    return [c["supplier_code"] for c in out["candidates"]]


def _spearman(a: list[str], b: list[str]) -> float | None:
    common = [x for x in a if x in b]
    n = len(common)
    if n < 2:
        return None
    ra = {x: i for i, x in enumerate([x for x in a if x in common])}
    rb = {x: i for i, x in enumerate([x for x in b if x in common])}
    d2 = sum((ra[x] - rb[x]) ** 2 for x in common)
    return 1 - 6 * d2 / (n * (n * n - 1))


def ablate() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cat in CATEGORIES:
        for preset, w in PRESETS.items():
            full = _ranking(cat, preset, None)
            if len(full) < 2:
                continue
            for crit in ALL_CRITERIA:
                if w.get(crit, 0) == 0:
                    continue                     # nothing to remove
                w2 = {k: v for k, v in w.items() if k != crit and v > 0}
                abl = _ranking(cat, preset, w2)
                rows.append({
                    "category": cat, "preset": preset, "removed": crit,
                    "weight_removed": w[crit], "n_candidates": len(full),
                    "winner_full": full[0], "winner_ablated": abl[0],
                    "winner_changed": int(full[0] != abl[0]),
                    "top3_overlap": len(set(full[:3]) & set(abl[:3])) / min(3, len(full)),
                    "spearman": _spearman(full, abl),
                })
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for crit in ALL_CRITERIA:
        rs = [r for r in rows if r["removed"] == crit]
        if not rs:
            continue
        sp = [r["spearman"] for r in rs if r["spearman"] is not None]
        out[crit] = {
            "cases": len(rs),
            "winner_change_rate": round(100 * sum(r["winner_changed"] for r in rs) / len(rs), 1),
            "top3_overlap": round(sum(r["top3_overlap"] for r in rs) / len(rs), 3),
            "spearman": round(sum(sp) / len(sp), 3) if sp else None,
            "changed_cases": [f"{r['category']}/{r['preset']}: {r['winner_full']}→{r['winner_ablated']}"
                              for r in rs if r["winner_changed"]],
        }
    return out


def write(rows: list[dict[str, Any]], out: Path) -> dict[str, dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "recommender_ablation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    s = summarize(rows)
    md = ["# Recommender ablation — criterion influence", "",
          f"{len(rows)} (category × preset × removed-criterion) cases over "
          f"{len(CATEGORIES)} categories and {len(PRESETS)} presets.", "",
          "| removed criterion | cases | winner changes | top-3 overlap | Spearman ρ |",
          "|---|---|---|---|---|"]
    for crit, v in sorted(s.items(), key=lambda kv: -kv[1]["winner_change_rate"]):
        md.append(f"| {crit} | {v['cases']} | {v['winner_change_rate']}% | "
                  f"{v['top3_overlap']} | {v['spearman']} |")
    ml = s.get("ml_risk")
    if ml:
        md += ["", "## ML-risk criterion", "",
               f"Removing the classifier changes the recommended supplier in "
               f"**{ml['winner_change_rate']}%** of cases "
               f"({len(ml['changed_cases'])}/{ml['cases']}); mean rank correlation "
               f"with the full model {ml['spearman']}.", ""]
        md += [f"- {c}" for c in ml["changed_cases"]]
    (out / "recommender_ablation.md").write_text("\n".join(md) + "\n")
    _plot(s, out)
    return s


def _plot(s: dict[str, dict[str, Any]], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    crits = sorted(s, key=lambda c: s[c]["winner_change_rate"])
    labels = {"ml_risk": "predicted risk (ML)", "reliability": "reliability (OTD)",
              "price": "price", "technical": "technical (TBE)", "lead_time": "lead time",
              "quality": "quality (QC)", "terms": "payment terms"}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    vals = [s[c]["winner_change_rate"] for c in crits]
    colors = [ACTION if c == "ml_risk" else NAVY for c in crits]
    ax.barh(range(len(crits)), vals, color=colors, height=0.6, edgecolor="white", linewidth=2)
    for i, (c, v) in enumerate(zip(crits, vals)):
        ax.text(v + 1, i, f"{v:.0f}%  (ρ {s[c]['spearman']})", va="center", fontsize=9,
                color="#334155")
    ax.set_yticks(range(len(crits)))
    ax.set_yticklabels([labels.get(c, c) for c in crits])
    ax.set_xlim(0, max(vals) + 22)
    ax.set_xlabel("share of category × preset cases whose recommended supplier changes")
    ax.set_title("Recommender ablation — which criteria actually move the decision",
                 loc="left")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout(); fig.savefig(out / "recommender_ablation.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench_results")
    a = ap.parse_args()
    rows = ablate()
    s = write(rows, Path(a.out))
    for crit, v in sorted(s.items(), key=lambda kv: -kv[1]["winner_change_rate"]):
        print(f"  {crit:12s} winner changes {v['winner_change_rate']:>5}%  "
              f"top3 overlap {v['top3_overlap']}  ρ {v['spearman']}")
    print(f"reports: {Path(a.out)}/recommender_ablation.{{csv,md,png}}")
