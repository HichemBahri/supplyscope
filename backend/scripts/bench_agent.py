"""Agent benchmark runner (Phase 15).

Runs every question in app.eval.questions through the real agent, grades
the result against ground truth computed live from the database, and
reports accuracy overall / by tier / by topic plus the self-correction
rescue rate.

Cost discipline: results are CACHED per (question, llm_tier) in a JSON
file, so an interrupted run resumes and a re-run only re-plots. Use
--force to re-query.

Usage:
    python -m scripts.bench_agent                    # fast tier, all questions
    python -m scripts.bench_agent --llm-tier smart   # compare model tiers
    python -m scripts.bench_agent --only M01,H02     # a subset
    python -m scripts.bench_agent --force            # ignore the cache

Outputs (in --out, default backend/bench_results/):
    agent_bench_<tier>.json   raw per-question records (the cache)
    agent_bench_<tier>.csv    per-question table for the thesis appendix
    agent_bench_<tier>.md     summary tables
    agent_bench_<tier>.png    accuracy-by-tier figure
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import psycopg

from app.config import get_settings
from app.eval.grader import grade
from app.eval.questions import QUESTIONS, TIERS, BenchQuestion

# project palette (design system parameters)
NAVY, ACTION, MUTED, WARN = "#0B2239", "#155E97", "#94A3B8", "#b97d10"


def truth_rows(q: BenchQuestion) -> list[list[Any]]:
    with psycopg.connect(get_settings().app_dsn) as c:
        return [list(r) for r in c.execute(q.truth_sql).fetchall()]


def _jsonable(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)


def run_question(q: BenchQuestion, ask_fn: Callable, llm_tier: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    a = ask_fn(q.question, llm_tier)
    wall = round((time.perf_counter() - t0) * 1000, 1)
    truth = truth_rows(q)
    agent_rows = [list(r) for r in (a.rows or [])]
    failed = bool(getattr(a, "failed", False))
    n_fail_attempts = len(getattr(a, "attempts", []) or [])
    verdict = grade(q.kind, truth, agent_rows, q.tolerance) if not failed \
        else type("V", (), {"correct": False, "reason": "agent gave up"})()
    outcome = ("failed" if failed else
               "rescued" if verdict.correct and n_fail_attempts > 0 else
               "first_try" if verdict.correct else "wrong")
    return {
        "qid": q.qid, "tier": q.tier, "topic": q.topic, "kind": q.kind,
        "question": q.question, "llm_tier": llm_tier,
        "sql": getattr(a, "sql", ""), "columns": list(getattr(a, "columns", []) or []),
        "rows": [[_jsonable(c) for c in r] for r in agent_rows[:20]],
        "row_count": getattr(a, "row_count", len(agent_rows)),
        "failed": failed, "failed_attempts": n_fail_attempts,
        "duration_ms": wall, "answer": (getattr(a, "answer", "") or "")[:400],
        "truth": [[_jsonable(c) for c in r] for r in truth[:10]],
        "correct": bool(verdict.correct), "reason": verdict.reason, "outcome": outcome,
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    def block(rs):
        n = len(rs)
        c = sum(r["correct"] for r in rs)
        return {"n": n, "correct": c, "accuracy": round(100 * c / n, 1) if n else 0.0,
                "first_try": sum(r["outcome"] == "first_try" for r in rs),
                "rescued": sum(r["outcome"] == "rescued" for r in rs),
                "wrong": sum(r["outcome"] == "wrong" for r in rs),
                "failed": sum(r["outcome"] == "failed" for r in rs)}
    by_tier = {t: block([r for r in records if r["tier"] == t]) for t in TIERS}
    topics = sorted({r["topic"] for r in records})
    by_topic = {t: block([r for r in records if r["topic"] == t]) for t in topics}
    overall = block(records)
    needed_fix = [r for r in records if r["failed_attempts"] > 0]
    rescue = {"needed_correction": len(needed_fix),
              "rescued": sum(r["outcome"] == "rescued" for r in needed_fix),
              "rescue_rate": round(100 * sum(r["outcome"] == "rescued" for r in needed_fix)
                                   / len(needed_fix), 1) if needed_fix else None}
    return {"overall": overall, "by_tier": by_tier, "by_topic": by_topic,
            "self_correction": rescue,
            "median_ms": sorted(r["duration_ms"] for r in records)[len(records) // 2]
            if records else None}


def write_reports(records: list[dict[str, Any]], out: Path, llm_tier: str,
                  chart: bool = True) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"agent_bench_{llm_tier}"
    s = summarize(records)
    # CSV — thesis appendix
    with open(stem.with_suffix(".csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["qid", "tier", "topic", "kind", "question", "outcome", "correct",
                    "failed_attempts", "duration_ms", "reason"])
        for r in sorted(records, key=lambda r: r["qid"]):
            w.writerow([r["qid"], r["tier"], r["topic"], r["kind"], r["question"],
                        r["outcome"], r["correct"], r["failed_attempts"],
                        r["duration_ms"], r["reason"]])
    # Markdown summary
    o = s["overall"]
    lines = [f"# Agent benchmark — llm tier `{llm_tier}`", "",
             f"**Overall accuracy: {o['accuracy']}%** ({o['correct']}/{o['n']}) · "
             f"first-try {o['first_try']} · rescued by self-correction {o['rescued']} · "
             f"wrong {o['wrong']} · gave up {o['failed']} · median latency {s['median_ms']} ms", "",
             "| tier | n | accuracy | first-try | rescued | wrong | gave up |",
             "|---|---|---|---|---|---|---|"]
    for t in TIERS:
        b = s["by_tier"][t]
        lines.append(f"| {t} | {b['n']} | {b['accuracy']}% | {b['first_try']} | "
                     f"{b['rescued']} | {b['wrong']} | {b['failed']} |")
    lines += ["", "| topic | n | accuracy |", "|---|---|---|"]
    for t, b in s["by_topic"].items():
        lines.append(f"| {t} | {b['n']} | {b['accuracy']}% |")
    sc = s["self_correction"]
    lines += ["", f"**Self-correction:** {sc['needed_correction']} questions needed at least one "
              f"SQL fix; {sc['rescued']} of those ended correct "
              f"(rescue rate {sc['rescue_rate']}%).", "",
              "## Failures", "", "| qid | tier | outcome | reason |", "|---|---|---|---|"]
    for r in sorted(records, key=lambda r: r["qid"]):
        if not r["correct"]:
            lines.append(f"| {r['qid']} | {r['tier']} | {r['outcome']} | {r['reason']} |")
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n")
    if chart:
        _plot(s, stem.with_suffix(".png"), llm_tier)
    return s


def _plot(s: dict[str, Any], path: Path, llm_tier: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tiers = list(TIERS)
    n = [s["by_tier"][t]["n"] or 1 for t in tiers]
    first = [100 * s["by_tier"][t]["first_try"] / n[i] for i, t in enumerate(tiers)]
    resc = [100 * s["by_tier"][t]["rescued"] / n[i] for i, t in enumerate(tiers)]
    miss = [100 - f - r for f, r in zip(first, resc)]

    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = range(len(tiers))
    seg = dict(height=0.55, edgecolor="white", linewidth=2)   # 2px surface gaps
    ax.barh(y, first, color=NAVY, label="correct, first try", **seg)
    ax.barh(y, resc, left=first, color=ACTION,
            label="correct after self-correction", **seg)
    ax.barh(y, miss, left=[f + r for f, r in zip(first, resc)], color=MUTED,
            label="incorrect / gave up", **seg)
    for i, t in enumerate(tiers):
        acc = s["by_tier"][t]["accuracy"]
        ax.text(101, i, f"{acc:.0f}%  (n={s['by_tier'][t]['n']})", va="center",
                fontsize=10, color="#334155")
    ax.set_yticks(list(y))
    ax.set_yticklabels([t.capitalize() for t in tiers])
    ax.invert_yaxis()
    ax.set_xlim(0, 125)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("share of questions (%)")
    ax.set_title(f"Agent accuracy by difficulty tier — overall "
                 f"{s['overall']['accuracy']:.0f}% ({llm_tier} model)", loc="left")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="upper center", bbox_to_anchor=(0.42, -0.22), ncol=3,
              frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _cache_path(out: Path, llm_tier: str, run_id: int) -> Path:
    # run 1 keeps the historical filename; further runs get a suffix
    return out / (f"agent_bench_{llm_tier}.json" if run_id == 1
                  else f"agent_bench_{llm_tier}_run{run_id}.json")


def _regrade(q: BenchQuestion, r: dict[str, Any]) -> dict[str, Any]:
    """Re-apply the grader to a cached answer (grader or truth may have
    changed; the LLM answer is kept, so this costs nothing)."""
    if r.get("failed"):
        return r
    truth = truth_rows(q)
    v = grade(q.kind, truth, [list(x) for x in r.get("rows", [])], q.tolerance)
    r = dict(r, correct=bool(v.correct), reason=v.reason,
             truth=[[_jsonable(c) for c in t] for t in truth[:10]])
    r["outcome"] = ("rescued" if v.correct and r["failed_attempts"] > 0 else
                    "first_try" if v.correct else "wrong")
    return r


def show(llm_tier: str, qids: set[str], out: Path = Path("bench_results"),
         run_id: int = 1) -> None:
    """Print the agent's SQL, columns, first rows and the truth for qids."""
    p = _cache_path(out, llm_tier, run_id)
    recs = {r["qid"]: r for r in json.loads(p.read_text())} if p.exists() else {}
    for qid in sorted(qids):
        r = recs.get(qid)
        if not r:
            print(f"--- {qid}: not in cache"); continue
        print(f"--- {qid} [{r['outcome']}] {r['question']}\n{r['sql']}\n"
              f"columns: {r['columns']}\nrows: {r['rows'][:5]}\ntruth: {r['truth'][:5]}\n")


def run(llm_tier: str = "fast", only: set[str] | None = None, limit: int | None = None,
        force: bool = False, out: Path = Path("bench_results"),
        ask_fn: Callable | None = None, chart: bool = True, run_id: int = 1,
        regrade: bool = False) -> dict[str, Any]:
    if ask_fn is None:
        from app.agent.runner import ask
        ask_fn = ask
    out.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(out, llm_tier, run_id)
    cache: dict[str, dict] = {}
    if cache_path.exists():                      # ALWAYS load: --force only
        cache = {r["qid"]: r for r in json.loads(cache_path.read_text())}
    todo = [q for q in QUESTIONS if (only is None or q.qid in only)]
    if limit:
        todo = todo[:limit]
    if regrade:                                  # re-grade cached rows, no LLM
        for q in todo:
            if q.qid in cache:
                cache[q.qid] = _regrade(q, cache[q.qid])
        cache_path.write_text(json.dumps(list(cache.values()), indent=1))
    for q in todo:
        if q.qid in cache and not (force and not regrade):
            r = cache[q.qid]
            print(f"  {q.qid} (cached)  {r['outcome']:9s} {r['reason']}")
            continue
        r = run_question(q, ask_fn, llm_tier)
        cache[q.qid] = r
        cache_path.write_text(json.dumps(list(cache.values()), indent=1))   # resumable
        print(f"  {q.qid} {r['duration_ms']:>7.0f}ms  {r['outcome']:9s} {r['reason']}")
    records = [cache[q.qid] for q in todo if q.qid in cache]
    s = write_reports(records, out, llm_tier if run_id == 1 else f"{llm_tier}_run{run_id}",
                      chart=chart)
    o = s["overall"]
    print(f"\nOverall {o['accuracy']}% ({o['correct']}/{o['n']}) — "
          + " · ".join(f"{t} {s['by_tier'][t]['accuracy']}%" for t in TIERS)
          + f" — rescue rate {s['self_correction']['rescue_rate']}%")
    print(f"reports: {out / f'agent_bench_{llm_tier}'}.{{json,csv,md,png}}")
    return s


def aggregate(out: Path = Path("bench_results"), tiers: tuple[str, ...] = ("fast", "smart"),
              chart: bool = True) -> dict[str, Any]:
    """Combine every available run per model tier: accuracy mean / min / max
    per difficulty tier, and per-question stability (fraction of runs
    correct) — the honest way to report a nondeterministic system."""
    result: dict[str, Any] = {}
    lines = ["# Agent benchmark — aggregate over runs", ""]
    for tier in tiers:
        runs = []
        for p in sorted(out.glob(f"agent_bench_{tier}*.json")):
            if "_run" in p.stem or p.stem == f"agent_bench_{tier}":
                recs = json.loads(p.read_text())
                if len(recs) >= len(QUESTIONS) * 0.9:        # complete runs only
                    runs.append({r["qid"]: r for r in recs})
        if not runs:
            continue
        per_q = {q.qid: sum(1 for run in runs if run.get(q.qid, {}).get("correct"))
                 for q in QUESTIONS}
        accs = {t: [] for t in ("overall", *TIERS)}
        for run in runs:
            recs = list(run.values())
            accs["overall"].append(100 * sum(r["correct"] for r in recs) / len(recs))
            for t in TIERS:
                rs = [r for r in recs if r["tier"] == t]
                accs[t].append(100 * sum(r["correct"] for r in rs) / len(rs))
        lat = sorted(r["duration_ms"] for run in runs for r in run.values())
        stats = {k: {"mean": round(sum(v) / len(v), 1), "min": round(min(v), 1),
                     "max": round(max(v), 1)} for k, v in accs.items()}
        unstable = sorted(q for q, c in per_q.items() if 0 < c < len(runs))
        always_wrong = sorted(q for q, c in per_q.items() if c == 0)
        result[tier] = {"runs": len(runs), "accuracy": stats,
                        "median_ms": lat[len(lat) // 2],
                        "unstable": unstable, "always_wrong": always_wrong,
                        "per_question": per_q}
        lines += [f"## `{tier}` — {len(runs)} run(s), median latency {lat[len(lat)//2]:.0f} ms", "",
                  "| scope | mean | min | max |", "|---|---|---|---|"]
        for k in ("overall", *TIERS):
            lines.append(f"| {k} | {stats[k]['mean']}% | {stats[k]['min']}% | {stats[k]['max']}% |")
        lines += ["", f"Always wrong (all runs): {', '.join(always_wrong) or '—'}",
                  f"Unstable (correct in some runs only): {', '.join(unstable) or '—'}", ""]
    (out / "agent_bench_aggregate.md").write_text("\n".join(lines) + "\n")
    if chart and result:
        _plot_aggregate(result, out / "agent_bench_aggregate.png")
    return result


def _plot_aggregate(result: dict[str, Any], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scopes = ["overall", *TIERS]
    tiers = [t for t in ("fast", "smart") if t in result]
    colors = {"fast": NAVY, "smart": ACTION}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    w = 0.36
    for i, tier in enumerate(tiers):
        st = result[tier]["accuracy"]
        means = [st[s]["mean"] for s in scopes]
        lo = [st[s]["mean"] - st[s]["min"] for s in scopes]
        hi = [st[s]["max"] - st[s]["mean"] for s in scopes]
        xs = [k + (i - (len(tiers) - 1) / 2) * w for k in range(len(scopes))]
        ax.bar(xs, means, width=w - 0.04, color=colors[tier], edgecolor="white",
               linewidth=2, label=f"{tier} model ({result[tier]['runs']} runs)")
        ax.errorbar(xs, means, yerr=[lo, hi], fmt="none", ecolor="#334155",
                    elinewidth=1.2, capsize=4)
        for x, m, h in zip(xs, means, hi):
            ax.text(x, m + h + 2.5, f"{m:.0f}", ha="center", fontsize=9, color="#334155")
    ax.set_xticks(range(len(scopes)))
    ax.set_xticklabels([s.capitalize() for s in scopes])
    ax.set_ylim(0, 115)
    ax.set_ylabel("accuracy (%)")
    ax.set_title("Agent accuracy by difficulty tier — mean over runs, min–max whiskers",
                 loc="left")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2,
              frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-tier", default="fast", choices=["fast", "smart"])
    ap.add_argument("--only", default=None, help="comma-separated qids")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default="bench_results")
    ap.add_argument("--no-chart", action="store_true")
    ap.add_argument("--run", type=int, default=1, help="run index (1 = default cache)")
    ap.add_argument("--regrade", action="store_true",
                    help="re-grade cached answers with the current grader/truth (no LLM)")
    ap.add_argument("--show", default=None, help="print cached SQL/rows/truth for qids")
    ap.add_argument("--aggregate", action="store_true",
                    help="combine all runs per tier: mean/min/max + stability")
    a = ap.parse_args()
    if a.show:
        show(a.llm_tier, set(a.show.split(",")), Path(a.out), a.run)
    elif a.aggregate:
        r = aggregate(Path(a.out), chart=not a.no_chart)
        for t, v in r.items():
            print(f"{t}: {v['runs']} runs, overall {v['accuracy']['overall']} | "
                  f"always wrong {v['always_wrong']} | unstable {v['unstable']}")
        print(f"reports: {Path(a.out) / 'agent_bench_aggregate'}.{{md,png}}")
    else:
        run(a.llm_tier, set(a.only.split(",")) if a.only else None, a.limit, a.force,
            Path(a.out), chart=not a.no_chart, run_id=a.run, regrade=a.regrade)
