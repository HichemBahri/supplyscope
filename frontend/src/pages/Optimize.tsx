/** Award Optimization — the OR pillar, live.
 *  Two sliders (delay penalty λ, risk ceiling) re-solve the MILP on
 *  release; the allocation table highlights where the solver diverged
 *  from cheapest to respect the risk policy. The demo: drag the ceiling
 *  down and watch awards jump from cheap-risky to costlier-safe. */
import { useCallback, useEffect, useRef, useState } from "react";
import { ShieldAlert, SlidersHorizontal, TrendingDown } from "lucide-react";
import { api } from "../lib/api";
import type { OptResponse } from "../lib/types";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

const fmtM = (v: number) => `${(v / 1e6).toFixed(2)}M`;
const fmtT = (v: number) => v.toLocaleString("fr-TN", { maximumFractionDigits: 0 });

export default function Optimize() {
  const [penalty, setPenalty] = useState(0.15);
  const [ceiling, setCeiling] = useState(0.65);
  const [data, setData] = useState<OptResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | null>(null);

  const solve = useCallback((p: number, c: number) => {
    setLoading(true);
    api.optimizeAwards(p, c).then(setData).finally(() => setLoading(false));
  }, []);
  useEffect(() => { solve(0.15, 0.65); }, [solve]);

  // debounce slider drags into one solve
  const onParam = (p: number, c: number) => {
    setPenalty(p); setCeiling(c);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => solve(p, c), 350);
  };

  const r = data?.constraints_report;

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <header className="mb-5">
          <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display">
            Operations research
          </p>
          <h1 className="text-2xl font-bold text-navy-900 font-display">
            Award Optimization
          </h1>
          <p className="text-sm text-ink-muted mt-1 max-w-3xl">
            Mixed-Integer Linear Programming over the contested RFQs of the last
            period: minimize expected cost (price + ML-predicted delay penalty)
            under one-award-per-RFQ, the expert-system concentration ceiling, and
            a hard risk policy. Solved exactly by CBC{data ? ` in ${data.solver_ms} ms` : ""}.
          </p>
        </header>

        {/* the two levers */}
        <Card className="p-4 mb-5">
          <div className="grid sm:grid-cols-2 gap-6">
            <label className="block">
              <div className="flex justify-between text-[12px] mb-1">
                <span className="font-semibold text-navy-900 inline-flex items-center gap-1.5">
                  <SlidersHorizontal className="size-3.5" /> Delay penalty λ
                </span>
                <span className="font-mono text-ink-muted">{penalty.toFixed(2)} × order value</span>
              </div>
              <input type="range" min={0} max={1} step={0.05} value={penalty}
                onChange={(e) => onParam(parseFloat(e.target.value), ceiling)}
                className="w-full accent-action" />
              <p className="text-[11px] text-ink-muted mt-1">
                Expected extra cost if an award arrives late.
              </p>
            </label>
            <label className="block">
              <div className="flex justify-between text-[12px] mb-1">
                <span className="font-semibold text-navy-900 inline-flex items-center gap-1.5">
                  <ShieldAlert className="size-3.5" /> Risk ceiling
                </span>
                <span className="font-mono text-ink-muted">p(late) ≤ {ceiling.toFixed(2)}</span>
              </div>
              <input type="range" min={0.3} max={0.9} step={0.05} value={ceiling}
                onChange={(e) => onParam(penalty, parseFloat(e.target.value))}
                className="w-full accent-action" />
              <p className="text-[11px] text-ink-muted mt-1">
                No award above this predicted risk when an alternative exists.
              </p>
            </label>
          </div>
        </Card>

        {loading && !data ? (
          <div className="p-10 flex justify-center"><Spinner /></div>
        ) : !data || data.status !== "Optimal" ? (
          <Card className="p-8 text-center text-sm text-ink-muted">
            {data?.note ?? `Solver status: ${data?.status ?? "…"}`}
          </Card>
        ) : (
          <>
            {/* headline + comparison strip */}
            <div className="grid sm:grid-cols-4 gap-3 mb-5">
              <Card className="px-4 py-3 border-action border-2">
                <p className="text-[10px] uppercase tracking-wider text-ink-muted">Optimized expected total</p>
                <p className="font-mono text-xl text-navy-900">{fmtM(data.totals.expected_total_tnd)} TND</p>
                <p className="text-[11px] text-ink-muted font-mono">avg p(late) {data.totals.avg_p_late.toFixed(3)}</p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-muted">Actual awards</p>
                <p className="font-mono text-xl text-navy-900">{fmtM(data.actual_allocation.expected_total_tnd)} TND</p>
                <p className="text-[11px] text-ink-muted font-mono">avg p(late) {data.actual_allocation.avg_p_late.toFixed(3)}</p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-muted">Naive cheapest</p>
                <p className="font-mono text-xl text-navy-900">{fmtM(data.baseline_cheapest.expected_total_tnd)} TND</p>
                <p className="text-[11px] text-ink-muted font-mono">avg p(late) {data.baseline_cheapest.avg_p_late.toFixed(3)}</p>
              </Card>
              <Card className="px-4 py-3 bg-ok/5">
                <p className="text-[10px] uppercase tracking-wider text-ink-muted inline-flex items-center gap-1">
                  <TrendingDown className="size-3" /> vs actual (expected)
                </p>
                <p className="font-mono text-xl text-ok">−{fmtM(data.savings_vs_actual_tnd)} TND</p>
                <p className="text-[11px] text-ink-muted font-mono">{data.savings_vs_actual_pct.toFixed(1)}% lower</p>
              </Card>
            </div>

            {/* constraints strip */}
            {r && (
              <p className="text-[12px] text-ink-muted mb-3 font-mono">
                {data.open_rfqs} RFQs · {data.candidate_bids} bids ·
                excluded by risk: <span className="text-danger font-semibold">{r.bids_excluded_by_risk}</span> ·
                diverged from cheapest: <span className="text-action font-semibold">{r.diverged_from_cheapest}</span> ·
                max supplier share {(r.max_supplier_share_actual * 100).toFixed(1)}% / {(r.concentration_ceiling * 100).toFixed(0)}% ({r.concentration_mode})
              </p>
            )}

            {/* allocation table */}
            <Card className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-ink-muted border-b border-line">
                    <th className="px-3 py-2 font-medium">RFQ</th>
                    <th className="px-3 py-2 font-medium">Category</th>
                    <th className="px-3 py-2 font-medium">Dest.</th>
                    <th className="px-3 py-2 font-medium">Awarded to</th>
                    <th className="px-3 py-2 font-medium text-right">Price (TND)</th>
                    <th className="px-3 py-2 font-medium text-right">p(late)</th>
                    <th className="px-3 py-2 font-medium text-right">Expected (TND)</th>
                    <th className="px-3 py-2 font-medium">Note</th>
                  </tr>
                </thead>
                <tbody>
                  {data.allocations.map((a) => (
                    <tr key={a.rfq_ref}
                      className={`border-b border-line/40 last:border-0 ${
                        !a.was_cheapest_bid ? "bg-action/5" : ""}`}>
                      <td className="px-3 py-1.5 font-mono">{a.rfq_ref}</td>
                      <td className="px-3 py-1.5">{a.category.replace(/_/g, " ")}</td>
                      <td className="px-3 py-1.5">{a.destination}</td>
                      <td className="px-3 py-1.5">{a.supplier_name}</td>
                      <td className="px-3 py-1.5 text-right font-mono">{fmtT(a.price_tnd)}</td>
                      <td className={`px-3 py-1.5 text-right font-mono ${
                        a.p_late > 0.5 ? "text-danger" : a.p_late > 0.3 ? "text-warn" : "text-ok"}`}>
                        {a.p_late.toFixed(3)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono">{fmtT(a.expected_cost_tnd)}</td>
                      <td className="px-3 py-1.5">
                        {!a.was_cheapest_bid ? (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-action/10 text-action border border-action/30">
                            risk override
                          </span>
                        ) : a.was_actual_award ? (
                          <span className="text-[10px] text-ink-muted">= actual award</span>
                        ) : (
                          <span className="text-[10px] text-ink-muted">≠ actual</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <p className="text-[11px] text-ink-muted mt-3">
              Highlighted rows: the solver deliberately passed over the cheapest
              bid to respect the risk ceiling — the ML model changing the
              decision. Savings are in expected terms; the optimizer may spend
              more cash than naive-cheapest to buy lower delivery risk.
            </p>
          </>
        )}
      </div>
    </main>
  );
}
