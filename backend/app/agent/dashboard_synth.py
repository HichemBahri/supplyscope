"""Agentic dashboard synthesis (Phase 13a).

The agent graduates from answering questions to BUILDING artifacts: given a
topic ("supplier performance"), it

  1. PLANS a coherent set of complementary views with the smart model —
     a KPI, a ranking, a trend, a breakdown — as structured JSON;
  2. EXECUTES each planned view through the existing agent graph — the
     same generate→execute→fix loop, the same read-only safe executor,
     the same chart validation; synthesis adds NO new security surface;
  3. ASSEMBLES the validated charts into a saved dashboard, which is
     live-reactive from the moment it exists (saved charts register in
     the dependency index like any other).

Partial failure is a feature, not an error: a planned view whose SQL
cannot be produced is skipped and reported; the dashboard ships with
whatever survived validation.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agent.runner import ask
from app.db import app_repo
from app.llm.factory import get_llm

logger = logging.getLogger("supplyscope.synth")

MAX_CHARTS = 6
MIN_CHARTS = 3

_PLAN_PROMPT = """You are the planning step of a BI dashboard generator for
an EPC supply-chain analytics platform. Data lives in PostgreSQL schemas:
erp (tenders, projects, boqs, rfqs, supplier_quotations, purchase_orders,
shipments, goods_receipts, payments, suppliers, materials, assets),
ml (delivery_risk predictions, price_forecast), es (alerts).

Topic requested by the user: {topic}

Design a dashboard of {min_c}-{max_c} COMPLEMENTARY views on this topic.

DATA AWARENESS — the dataset is a 5-year history of a mid-size contractor
(hundreds of orders, not millions). Therefore:
- for rates/percentages over time, use QUARTERLY granularity, never monthly;
- ranking questions must require a minimum sample (e.g. at least 5
  deliveries) so tiny histories cannot dominate;
- ask only questions answerable from ONE schema's tables joined on real
  keys; do not invent joins between erp prices and ml forecasts;
- never combine two metrics of very different scales (e.g. a 0-100%
  rate with a near-zero variance) in ONE chart — one metric per view;
- the supplier base is SMALL (about 17 active suppliers): never ask for
  banded histograms or distributions OVER suppliers — the bands collapse
  into one or two buckets; ask direct rankings instead;
- any signed metric (delays that can be early, variances) must state the
  sign convention inside the question so the chart title carries it;
- SCHEMA GROUNDING: this is a purchasing/ERP schema with NO earned-value
  or physical-progress data. NEVER ask for CPI, SPI, earned value, schedule
  variance or any EVM metric — they cannot be computed and the agent will
  invent a formula. Supported cost views are: committed PO spend vs
  contract value (FX-normalized), budget utilisation %, projects over
  budget, spend by category, delivered-but-unpaid amounts in TND, PO price
  vs quoted price. Do not relabel a spend share as an "overrun".
- a question whose answer would be a single entity's flat line is a bad
  view; prefer aggregations with guaranteed non-empty results.
Good dashboards mix granularities: one headline KPI, one ranking or
comparison, one trend over time, one categorical breakdown. Each view is
a natural-language question the analytics agent will answer with SQL.

Answer ONLY with JSON, no prose, exactly this shape:
{{"title": "...", "description": "...",
  "views": [{{"question": "...", "kind": "kpi|ranking|trend|breakdown"}}]}}
"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("planner returned no JSON")
    return json.loads(m.group(0))


def plan_dashboard(topic: str, llm=None) -> dict:
    llm = llm or get_llm("smart")
    raw = llm.invoke(_PLAN_PROMPT.format(
        topic=topic, min_c=MIN_CHARTS, max_c=MAX_CHARTS)).content
    plan = _extract_json(raw if isinstance(raw, str) else str(raw))
    views = plan.get("views", [])[:MAX_CHARTS]
    if len(views) < 1:
        raise ValueError("planner produced no views")
    plan["views"] = views
    return plan


def synthesize_dashboard(topic: str, user_id: int,
                         llm=None, ask_fn=None) -> dict[str, Any]:
    """Plan → execute each view via the agent → assemble a live dashboard.
    `llm` and `ask_fn` are injectable for tests."""
    ask_fn = ask_fn or ask
    plan = plan_dashboard(topic, llm)
    dash = app_repo.create_dashboard(
        user_id, plan.get("title", f"Dashboard — {topic}")[:120],
        plan.get("description", f"Auto-generated on: {topic}")[:400])
    created, failed = [], []
    for view in plan["views"]:
        q = view.get("question", "").strip()
        if not q:
            continue
        try:
            a = ask_fn(q, "fast")
            if a.failed or not a.chart:
                raise RuntimeError(a.answer or "agent could not answer")
            rows = getattr(a, "rows", None) or []
            cols = getattr(a, "columns", []) or []

            def _metric_idx() -> int:
                m = ((a.chart.get("y_fields") or [None])[0]
                     or a.chart.get("value_field"))
                return cols.index(m) if m in cols else len(cols) - 1

            # degenerate-rate gate: a rate/percentage that is zero on every
            # row is arithmetically suspect (integer division truncates to
            # 0 in SQL) or an empty window — never ship it
            rate_ctx = any(w in (q + " " + str(a.chart.get("title", ""))
                                 ).lower()
                           for w in ("rate", "percent", "%", "ratio",
                                     "share"))
            if rate_ctx and rows and cols:
                mi = _metric_idx()

                def _zero(v) -> bool:
                    if v is None:      # NULL rate = empty window: equally
                        return True    # degenerate, ships as a fake "0%"
                    try:
                        return float(v) == 0.0
                    except (TypeError, ValueError):
                        return False
                if all(_zero(r[mi]) for r in rows):
                    raise RuntimeError(
                        "degenerate zero-valued rate — integer division "
                        "or empty time window suspected; view dropped")

            # auto-repair: a multi-entity line WITHOUT color_field gets the
            # entity column set deterministically — we do not rely on the
            # model obeying the prompt for chart validity
            if (a.chart.get("chart_type") == "line"
                    and not a.chart.get("color_field") and len(cols) >= 3
                    and rows):
                used = {a.chart.get("x_field")} | set(
                    a.chart.get("y_fields") or [])
                for ci, cname in enumerate(cols):
                    if cname in used:
                        continue
                    if isinstance(rows[0][ci], str):
                        a.chart["color_field"] = cname
                        logger.info("synth auto-repair: color_field=%s "
                                    "for %r", cname, q[:60])
                        break

            # mixed-scale repair: a bar/line with several y_fields whose
            # magnitudes differ by >100x cannot share one axis — the small
            # series renders as an invisible sliver. Keep the dominant ones.
            yf = a.chart.get("y_fields") or []
            if a.chart.get("chart_type") in ("bar", "line") and len(yf) > 1 \
                    and rows:
                def _mx(f):
                    i = cols.index(f) if f in cols else -1
                    vals = []
                    for r in rows:
                        try:
                            vals.append(abs(float(r[i])))
                        except (TypeError, ValueError, IndexError):
                            pass
                    return max(vals) if vals else 0.0
                tops = {f: _mx(f) for f in yf}
                big = max(tops.values()) or 1.0
                keep = [f for f in yf if tops[f] >= big / 100.0]
                if keep and len(keep) < len(yf):
                    logger.info("synth repair: dropped mixed-scale series %s",
                                [f for f in yf if f not in keep])
                    a.chart["y_fields"] = keep

            ctx = (q + " " + str(a.chart.get("title", ""))).lower()

            # (4) pie -> bar above 6 slices: pies stop being readable and
            # labels pile up; a bar carries the same data legibly
            if a.chart.get("chart_type") == "pie" and len(rows) > 6:
                a.chart = {"chart_type": "bar",
                           "title": a.chart.get("title", q[:80]),
                           "x_field": a.chart.get("label_field"),
                           "y_fields": [a.chart.get("value_field")],
                           "orientation": "h", "stacked": False}
                logger.info("synth repair: pie(%d) -> horizontal bar",
                            len(rows))

            if rows and cols:
                mi = _metric_idx()
                vals = []
                for r in rows:
                    try:
                        vals.append(float(r[mi]))
                    except (TypeError, ValueError):
                        pass

                # (2) money-magnitude gate: a metric named as an AMOUNT whose
                # values all sit below 100 is not money — a units/ratio
                # error dressed as currency (field case: exposure at 0.01)
                money_ctx = any(w in ctx for w in (
                    "amount", "spend", "exposure", "liability", "cost",
                    "budget", "revenue", "tnd", "value", "price"))
                ratio_ctx = any(w in ctx for w in (
                    "rate", "percent", "%", "ratio", "share", "index",
                    "variance", "count", "number"))
                if (money_ctx and not ratio_ctx and vals
                        and max(abs(v) for v in vals) < 100):
                    raise RuntimeError(
                        "implausible magnitude for a monetary metric "
                        "(all values < 100) — units error suspected; "
                        "view dropped")

                # (3) near-constant gate: a ranking where almost everyone
                # ties carries no information
                if len(rows) >= 10 and len({str(r[mi]) for r in rows}) <= 2:
                    raise RuntimeError(
                        f"uninformative: at most 2 distinct values across "
                        f"{len(rows)} rows — view dropped")

            if len(rows) > 2 and cols:
                idx = _metric_idx()
                if len({str(r[idx]) for r in rows}) == 1:
                    raise RuntimeError(
                        "uninformative: metric is constant across all "
                        "rows — view dropped")
            if getattr(a, "row_count", 1) == 0:
                raise RuntimeError("query returned no data — view dropped "
                                   "rather than shipping an empty chart")
            chart = app_repo.create_saved_chart(
                user_id, a.chart.get("title", q)[:120], a.sql, a.chart)
            app_repo.add_chart_to_dashboard(dash["dashboard_id"],
                                            chart["chart_id"])
            created.append({"question": q, "chart_id": chart["chart_id"],
                            "chart_type": a.chart.get("chart_type")})
        except Exception as e:                          # noqa: BLE001
            logger.warning("synth view failed: %s (%s)", q, e)
            failed.append({"question": q, "reason": str(e)[:200]})
    return {"dashboard_id": dash["dashboard_id"],
            "title": dash["title"],
            "planned": len(plan["views"]),
            "created": created, "failed": failed}
