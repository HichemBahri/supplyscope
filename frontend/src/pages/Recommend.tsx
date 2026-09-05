/** Supplier Recommendation — decision support the jury can audit.
 *  Every ranked card carries a stacked bar where each segment IS one
 *  criterion's contribution to the score: the explanation is the chart.
 *  Deciders (admin/manager) approve a supplier; the decision lands in the
 *  audit trail with a followed-the-recommendation flag. */
import { useCallback, useEffect, useState } from "react";
import { Award, CheckCircle2, Scale } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { RecoCandidate, RecoResponse } from "../lib/types";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

const CATEGORIES = ["steel", "electrical", "instrumentation", "safety",
  "piping", "valves", "mechanical_equipment", "welding_consumables"];
const PRESETS = [
  { id: "balanced", label: "Balanced" },
  { id: "cost_focused", label: "Cost-focused" },
  { id: "schedule_focused", label: "Schedule-focused" },
];
const DESTS = ["Tunisie", "Libye"];

// one stable color per criterion (distinct from severity + liveness hues)
const CRIT_COLOR: Record<string, string> = {
  reliability: "#155e97", ml_risk: "#7c3aed", price: "#0e7490",
  technical: "#3f6212", lead_time: "#9a3412", quality: "#a16207",
  terms: "#64748b",
};
const CRIT_LABEL: Record<string, string> = {
  reliability: "Reliability (OTD)", ml_risk: "Predicted risk (ML)",
  price: "Price", technical: "Technical (TBE)", lead_time: "Lead time",
  quality: "Quality (QC)", terms: "Payment terms",
};

export default function Recommend() {
  const { user } = useAuth();
  const [category, setCategory] = useState("steel");
  const [preset, setPreset] = useState("balanced");
  const [dest, setDest] = useState("Tunisie");
  const [data, setData] = useState<RecoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [approved, setApproved] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setApproved(null);
    api.recoSuppliers(category, preset, dest)
      .then(setData)
      .finally(() => setLoading(false));
  }, [category, preset, dest]);
  useEffect(() => { load(); }, [load]);

  const approve = async (c: RecoCandidate) => {
    await api.recoDecision({
      category, preset, supplier_code: c.supplier_code,
      top_ranked: data?.candidates[0]?.supplier_code ?? null,
    });
    setApproved(c.supplier_code);
  };

  const isDecider = user?.role === "admin" || user?.role === "manager";

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-5">
          <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display">
            Decision support
          </p>
          <h1 className="text-2xl font-bold text-navy-900 font-display">
            Supplier Recommendation
          </h1>
          <p className="text-sm text-ink-muted mt-1 max-w-2xl">
            Multi-criteria ranking (Simple Additive Weighting) over the recorded
            procurement history: TBE gate, seven weighted criteria including the
            live ML risk model. Every score decomposes into the bar below it.
          </p>
        </header>

        {/* controls */}
        <div className="flex flex-wrap items-center gap-2 mb-2">
          {CATEGORIES.map((c) => (
            <button key={c} onClick={() => setCategory(c)}
              className={`text-[12px] px-3 py-1 rounded-full border transition-colors ${
                c === category ? "bg-navy-900 text-white border-navy-900"
                : "bg-card text-ink-muted border-line hover:border-navy-700"}`}>
              {c.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 mb-5">
          <span className="text-[11px] uppercase tracking-wider text-ink-muted">Profile</span>
          {PRESETS.map((p) => (
            <button key={p.id} onClick={() => setPreset(p.id)}
              className={`text-[12px] px-3 py-1 rounded-full border transition-colors ${
                p.id === preset ? "bg-action text-white border-action"
                : "bg-card text-ink-muted border-line hover:border-action"}`}>
              {p.label}
            </button>
          ))}
          <span className="text-[11px] uppercase tracking-wider text-ink-muted ml-3">Destination</span>
          {DESTS.map((d) => (
            <button key={d} onClick={() => setDest(d)}
              className={`text-[12px] px-3 py-1 rounded-full border transition-colors ${
                d === dest ? "bg-navy-900 text-white border-navy-900"
                : "bg-card text-ink-muted border-line hover:border-navy-700"}`}>
              {d}
            </button>
          ))}
        </div>

        {/* legend */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 mb-4">
          {Object.entries(CRIT_LABEL).map(([k, label]) => (
            <span key={k} className="inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
              <span className="size-2.5 rounded-sm" style={{ background: CRIT_COLOR[k] }} />
              {label}
            </span>
          ))}
        </div>

        {loading || !data ? (
          <div className="p-10 flex justify-center"><Spinner /></div>
        ) : data.candidates.length === 0 ? (
          <Card className="p-8 text-center text-sm text-ink-muted">
            {data.note ?? "No TBE-qualified supplier history for this category."}
          </Card>
        ) : (
          <div className="space-y-3">
            {data.candidates.map((c, i) => (
              <Card key={c.supplier_id}
                className={`p-4 ${i === 0 ? "border-action border-2" : ""}`}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`size-8 shrink-0 rounded-full grid place-items-center font-mono text-sm ${
                      i === 0 ? "bg-action text-white" : "bg-navy-900/5 text-ink-muted"}`}>
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-navy-900 truncate">{c.name}</h3>
                        {i === 0 && <Award className="size-4 text-action" />}
                        {c.cold_start && (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-warn/10 text-warn border border-warn/30">
                            Limited history
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-ink-muted font-mono">
                        {c.supplier_code} · {c.country} · {c.evidence.category_quotes} quotes
                        · {c.evidence.delivered_shipments} deliveries
                        · {c.evidence.qc_receipts} QC receipts
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-2xl text-navy-900">{c.score.toFixed(3)}</span>
                    {isDecider && (
                      approved === c.supplier_code ? (
                        <span className="inline-flex items-center gap-1 text-[12px] font-semibold text-ok">
                          <CheckCircle2 className="size-4" /> Recorded
                        </span>
                      ) : (
                        <Button variant="ghost" disabled={!!approved}
                          onClick={() => approve(c)}>
                          <Scale className="size-4" /> Approve
                        </Button>
                      )
                    )}
                  </div>
                </div>

                {/* stacked contribution bar — the explanation IS the chart */}
                <button className="w-full mt-3" onClick={() => setOpen(open === c.supplier_id ? null : c.supplier_id)}
                  title="Click for the full criterion table">
                  <div className="h-3.5 w-full rounded-full bg-line/60 overflow-hidden flex">
                    {c.breakdown.filter((b) => b.contribution > 0).map((b) => (
                      <div key={b.criterion}
                        style={{ width: `${b.contribution * 100}%`,
                                 background: CRIT_COLOR[b.criterion] ?? "#94a3b8" }}
                        title={`${CRIT_LABEL[b.criterion] ?? b.criterion}: +${b.contribution.toFixed(3)}`} />
                    ))}
                  </div>
                </button>

                {open === c.supplier_id && (
                  <table className="w-full text-[12px] mt-3">
                    <thead>
                      <tr className="text-left text-[10px] uppercase tracking-wider text-ink-muted border-b border-line">
                        <th className="py-1 font-medium">Criterion</th>
                        <th className="py-1 font-medium text-right">Raw</th>
                        <th className="py-1 font-medium text-right">Normalized</th>
                        <th className="py-1 font-medium text-right">Weight</th>
                        <th className="py-1 font-medium text-right">Contribution</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.breakdown.map((b) => (
                        <tr key={b.criterion} className="border-b border-line/40 last:border-0">
                          <td className="py-1.5">
                            <span className="inline-flex items-center gap-1.5">
                              <span className="size-2 rounded-sm" style={{ background: CRIT_COLOR[b.criterion] }} />
                              {CRIT_LABEL[b.criterion] ?? b.criterion}
                              <span className="text-ink-muted">({b.direction})</span>
                            </span>
                          </td>
                          <td className="py-1.5 text-right font-mono">{b.raw ?? "—"}</td>
                          <td className="py-1.5 text-right font-mono">{b.normalized.toFixed(3)}</td>
                          <td className="py-1.5 text-right font-mono">{b.weight.toFixed(3)}</td>
                          <td className="py-1.5 text-right font-mono font-semibold">+{b.contribution.toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            ))}
            <p className="text-[11px] text-ink-muted">
              Method: {data.method} · ML risk criterion {data.ml_risk_included ? "active" : "unavailable"} ·
              eligibility: TBE ≥ 70, demonstrated category capability, active suppliers only.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
