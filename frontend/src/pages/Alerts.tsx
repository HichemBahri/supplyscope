/** Alerts — the expert-system console.
 *  A severity-tiered feed of rule-based alerts with the full lifecycle
 *  (active → acknowledged → resolved), refreshed LIVE via the same SSE
 *  stream that powers reactive charts. The rule catalog at the bottom is
 *  the thesis exhibit: seven declarative rules, each with its rationale. */
import { useCallback, useEffect, useState } from "react";
import { BellRing, CheckCheck, RefreshCcw, ShieldAlert } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useChartStream } from "../lib/useChartStream";
import type { Alert, AlertRule, AlertSummary } from "../lib/types";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

const SEV = {
  critical: { label: "Critical", accent: "border-l-danger", chip: "bg-danger/10 text-danger border-danger/30" },
  warning: { label: "Warning", accent: "border-l-warn", chip: "bg-warn/10 text-warn border-warn/30" },
  info: { label: "Info", accent: "border-l-action", chip: "bg-action/10 text-action border-action/30" },
} as const;

type Filter = "all" | "critical" | "warning" | "info" | "acknowledged";

export default function Alerts() {
  const { user } = useAuth();
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState(false);
  const [stamp, setStamp] = useState<Date | null>(null);

  const load = useCallback(() => {
    Promise.all([api.alerts(), api.alertsSummary(), api.alertRules()])
      .then(([a, s, r]) => { setAlerts(a); setSummary(s); setRules(r); setStamp(new Date()); })
      .catch(() => { setAlerts([]); setSummary(null); });
  }, []);
  useEffect(() => { load(); }, [load]);

  // live: the reactivity stream announces rule re-evaluations
  useChartStream(() => {}, undefined);
  useEffect(() => {
    const h = () => load();
    window.addEventListener("ss-alerts", h);
    return () => window.removeEventListener("ss-alerts", h);
  }, [load]);

  const ack = async (id: number) => {
    await api.ackAlert(id);
    load();
  };
  const evaluate = async () => {
    setBusy(true);
    try { await api.evaluateAlerts(); load(); } finally { setBusy(false); }
  };

  const visible = (alerts ?? []).filter((a) =>
    filter === "all" ? true
    : filter === "acknowledged" ? a.status === "acknowledged"
    : a.severity === filter);

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display">
              Expert system
            </p>
            <h1 className="text-2xl font-bold text-navy-900 font-display">Alerts</h1>
            <p className="text-sm text-ink-muted mt-1">
              Business rules evaluated continuously over live data — alerts
              appear here the moment a condition is breached.
              {stamp && (
                <span className="ml-2 font-mono text-[11px]">
                  refreshed {stamp.toLocaleTimeString()}
                </span>
              )}
            </p>
          </div>
          {user?.role === "admin" && (
            <Button variant="ghost" disabled={busy} onClick={evaluate}>
              <RefreshCcw className="size-4" />
              {busy ? "Evaluating…" : "Evaluate now"}
            </Button>
          )}
        </header>

        {/* summary strip */}
        {summary && (
          <div className="grid grid-cols-3 gap-3 mb-6">
            {(["critical", "warning", "info"] as const).map((s) => (
              <Card key={s} className="px-4 py-3 flex items-center justify-between">
                <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${SEV[s].chip}`}>
                  {SEV[s].label}
                </span>
                <span className="font-mono text-2xl text-navy-900">{summary[s]}</span>
              </Card>
            ))}
          </div>
        )}

        {/* filter pills */}
        <div className="flex gap-1.5 mb-4">
          {(["all", "critical", "warning", "info", "acknowledged"] as Filter[]).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`text-[12px] px-3 py-1 rounded-full border capitalize transition-colors ${
                f === filter
                  ? "bg-navy-900 text-white border-navy-900"
                  : "bg-card text-ink-muted border-line hover:border-navy-700"}`}>
              {f}
            </button>
          ))}
        </div>

        {/* feed */}
        {alerts === null ? (
          <div className="p-10 flex justify-center"><Spinner /></div>
        ) : visible.length === 0 ? (
          <Card className="p-8 text-center text-sm text-ink-muted">
            <ShieldAlert className="size-6 mx-auto mb-2 text-ok" />
            No {filter === "all" ? "active" : filter} alerts — all clear.
          </Card>
        ) : (
          <div className="space-y-3">
            {visible.map((a) => (
              <Card key={a.alert_id}
                className={`p-4 border-l-4 ${SEV[a.severity].accent}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${SEV[a.severity].chip}`}>
                        {SEV[a.severity].label}
                      </span>
                      <span className="font-mono text-[11px] text-ink-muted">
                        {a.rule_code} · {a.entity_ref}
                      </span>
                      {a.status === "acknowledged" && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-ok/10 text-ok border border-ok/30">
                          Acknowledged
                        </span>
                      )}
                    </div>
                    <h3 className="font-semibold text-navy-900 mt-1.5">{a.title}</h3>
                    <p className="text-sm text-ink mt-1 leading-relaxed">{a.detail}</p>
                    <p className="text-[11px] text-ink-muted mt-2 font-mono">
                      first seen {new Date(a.first_seen).toLocaleString()} ·
                      last confirmed {new Date(a.last_seen).toLocaleString()}
                    </p>
                  </div>
                  {a.status === "active" && (
                    <Button variant="ghost" onClick={() => ack(a.alert_id)}>
                      <CheckCheck className="size-4" /> Acknowledge
                    </Button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* rule catalog */}
        <section className="mt-10">
          <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display mb-2">
            Rule catalog — {rules.length} declarative rules
          </p>
          <Card className="divide-y divide-line/60">
            {rules.map((r) => (
              <div key={r.code} className="px-4 py-3 flex items-start gap-3">
                <BellRing className="size-4 mt-0.5 text-ink-muted shrink-0" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-navy-900">{r.name}</span>
                    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${SEV[r.severity as keyof typeof SEV].chip}`}>
                      {r.severity}
                    </span>
                    <span className="font-mono text-[10px] text-ink-muted">{r.code}</span>
                  </div>
                  <p className="text-[13px] text-ink-muted mt-0.5">{r.description}</p>
                </div>
              </div>
            ))}
          </Card>
        </section>
      </div>
    </main>
  );
}
