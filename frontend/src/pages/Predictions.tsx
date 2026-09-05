/** Predictions — the ML control room.
 *  Left: late-delivery risk for open shipments (active classifier).
 *  Right: model card — metrics, baseline ladder, permutation importances.
 *  Below: material price-index history + 6-month forecast per category.
 *  Risk severity uses danger/warn tones; safety orange stays liveness-only. */
import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { RefreshCcw, FlaskConical, TrendingUp } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { ForecastPoint, MlModel, RiskPrediction } from "../lib/types";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

const ForecastChart = lazy(() => import("../components/ForecastChart"));

const BAND = {
  high: { label: "High", cls: "bg-danger/10 text-danger border-danger/30" },
  medium: { label: "Medium", cls: "bg-warn/10 text-warn border-warn/30" },
  low: { label: "Low", cls: "bg-ok/10 text-ok border-ok/30" },
} as const;

const CATEGORIES = ["steel", "safety", "instrumentation", "electrical"];

export default function Predictions() {
  const { user } = useAuth();
  const [preds, setPreds] = useState<RiskPrediction[] | null>(null);
  const [models, setModels] = useState<MlModel[] | null>(null);
  const [forecast, setForecast] = useState<ForecastPoint[] | null>(null);
  const [category, setCategory] = useState("steel");
  const [busy, setBusy] = useState<string | null>(null);
  const [stamp, setStamp] = useState<Date | null>(null);

  const load = useCallback(() => {
    Promise.all([api.mlPredictions(), api.mlModels(), api.mlForecast()])
      .then(([p, m, f]) => { setPreds(p); setModels(m); setForecast(f); setStamp(new Date()); })
      .catch(() => { setPreds([]); setModels([]); setForecast([]); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (name: string, fn: () => Promise<unknown>) => {
    setBusy(name);
    try { await fn(); load(); } finally { setBusy(null); }
  };

  const risk = models?.find((m) => m.model_name === "delivery_risk" && m.is_active);
  const priceModel = models?.find((m) => m.model_name === "price_forecast" && m.is_active);
  const points = (forecast ?? []).filter((p) => p.category === category);
  const backtest = priceModel?.comparison?.[category] as
    Record<string, { mae: number; rmse: number; mape_pct: number }> | undefined;
  const bestAlgo = backtest
    ? Object.entries(backtest).sort((a, b) => a[1].mae - b[1].mae)[0][0]
    : null;

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display">
              Machine learning
            </p>
            <h1 className="text-2xl font-bold text-navy-900 font-display">Predictions</h1>
            <p className="text-sm text-ink-muted mt-1">
              Model outputs are ordinary data here. The assistant can query them, and
              charts built on them refresh live.
              {stamp && (
                <span className="ml-2 font-mono text-[11px]">
                  refreshed {stamp.toLocaleTimeString()}
                </span>
              )}
            </p>
          </div>
          {user?.role === "admin" && (
            <div className="flex gap-2">
              <Button variant="ghost" disabled={busy !== null}
                onClick={() => act("train", api.mlTrain)}>
                <FlaskConical className="size-4" />
                {busy === "train" ? "Training…" : "Retrain classifier"}
              </Button>
              <Button variant="ghost" disabled={busy !== null}
                onClick={() => act("score", api.mlScore)}>
                <RefreshCcw className="size-4" />
                {busy === "score" ? "Scoring…" : "Rescore open orders"}
              </Button>
              <Button variant="ghost" disabled={busy !== null}
                onClick={() => act("forecast", api.mlTrainForecast)}>
                <TrendingUp className="size-4" />
                {busy === "forecast" ? "Backtesting…" : "Refresh forecasts"}
              </Button>
            </div>
          )}
        </header>

        {/* ------------------------------------------------ delivery risk */}
        <section className="grid gap-6 lg:grid-cols-[1fr_320px] items-start">
          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-line">
              <h2 className="font-semibold text-navy-900 font-display">
                Late-delivery risk : open shipments
              </h2>
              <p className="text-xs text-ink-muted mt-0.5">
                Probability that each undelivered shipment misses its promised date.
              </p>
            </div>
            {preds === null ? (
              <div className="p-10 flex justify-center"><Spinner /></div>
            ) : preds.length === 0 ? (
              <p className="p-6 text-sm text-ink-muted">
                No predictions yet — train the classifier, then score open orders.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-ink-muted border-b border-line">
                    <th className="px-5 py-2 font-medium">Shipment</th>
                    <th className="px-2 py-2 font-medium">Supplier</th>
                    <th className="px-2 py-2 font-medium">Promised</th>
                    <th className="px-2 py-2 font-medium">Status</th>
                    <th className="px-2 py-2 font-medium w-44">Risk</th>
                    <th className="px-5 py-2 font-medium text-right">Band</th>
                  </tr>
                </thead>
                <tbody>
                  {preds.map((p) => (
                    <tr key={p.prediction_id} className="border-b border-line/60 last:border-0">
                      <td className="px-5 py-3">
                        <div className="font-mono text-[13px] text-navy-900">{p.shipment_ref}</div>
                        <div className="text-[11px] text-ink-muted font-mono">
                          {p.po_number}{p.project_code ? ` · ${p.project_code}` : ""}
                        </div>
                      </td>
                      <td className="px-2 py-3">{p.supplier_name}</td>
                      <td className="px-2 py-3 font-mono text-[13px]">
                        {p.promised_delivery_date ?? "—"}
                      </td>
                      <td className="px-2 py-3">
                        <span className="text-[11px] px-2 py-0.5 rounded-full bg-navy-900/5 text-ink-muted">
                          {(p.status ?? "").replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-2 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 rounded-full bg-line overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                p.risk_band === "high" ? "bg-danger"
                                : p.risk_band === "medium" ? "bg-warn" : "bg-ok"}`}
                              style={{ width: `${Math.round(Number(p.probability) * 100)}%` }}
                            />
                          </div>
                          <span className="font-mono text-[12px] w-10 text-right">
                            {(Number(p.probability) * 100).toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${BAND[p.risk_band].cls}`}>
                          {BAND[p.risk_band].label}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          {/* ------------------------------------------------ model card */}
          <Card className="p-5">
            <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display">
              Active model
            </p>
            {!risk ? (
              <p className="text-sm text-ink-muted mt-2">No classifier trained yet.</p>
            ) : (
              <>
                <h3 className="font-semibold text-navy-900 mt-1">
                  {risk.algo.replace(/_/g, " ")}
                  <span className="ml-2 font-mono text-[11px] text-ink-muted">v{risk.version}</span>
                </h3>
                <p className="text-[11px] text-ink-muted">
                  time split {risk.split_date} · {risk.train_rows} train / {risk.test_rows} test
                </p>
                <div className="grid grid-cols-2 gap-2 mt-3">
                  {(["roc_auc", "precision", "recall", "f1"] as const).map((k) => (
                    <div key={k} className="rounded-lg bg-canvas px-3 py-2">
                      <div className="text-[10px] uppercase tracking-wider text-ink-muted">
                        {k === "roc_auc" ? "ROC-AUC" : k}
                      </div>
                      <div className="font-mono text-lg text-navy-900">
                        {Number(risk.metrics[k]).toFixed(3)}
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display mt-4">
                  Baseline ladder (test ROC-AUC)
                </p>
                <div className="mt-1 space-y-1">
                  {Object.entries(risk.comparison as Record<string, { roc_auc: number }>)
                    .sort((a, b) => Number(b[1].roc_auc) - Number(a[1].roc_auc))
                    .map(([name, m]) => (
                      <div key={name} className="flex items-center justify-between text-[13px]">
                        <span className={name === risk.algo ? "font-semibold text-navy-900" : "text-ink-muted"}>
                          {name.replace(/_/g, " ")}
                        </span>
                        <span className="font-mono">{Number(m.roc_auc).toFixed(3)}</span>
                      </div>
                    ))}
                </div>
                {risk.feature_importance?.length > 0 && (
                  <>
                    <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display mt-4">
                      Top signals (permutation)
                    </p>
                    <div className="mt-1 space-y-1.5">
                      {risk.feature_importance.slice(0, 6).map((f) => {
                        const max = Number(risk.feature_importance[0].importance) || 1;
                        return (
                          <div key={f.feature}>
                            <div className="flex justify-between text-[11px]">
                              <span className="text-ink">{f.feature}</span>
                              <span className="font-mono text-ink-muted">
                                {Number(f.importance).toFixed(3)}
                              </span>
                            </div>
                            <div className="h-1 rounded-full bg-line overflow-hidden">
                              <div className="h-full bg-action rounded-full"
                                style={{ width: `${Math.max(4, (Number(f.importance) / max) * 100)}%` }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </>
            )}
          </Card>
        </section>

        {/* ------------------------------------------------ price forecast */}
        <section className="mt-8">
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold text-navy-900 font-display">
                  Material price index : 6-month forecast
                </h2>
                <p className="text-xs text-ink-muted mt-0.5">
                  Median unit price vs reference, monthly. Winner of an expanding-window
                  backtest projects the dashed segment.
                </p>
              </div>
              <div className="flex gap-1.5">
                {CATEGORIES.map((c) => (
                  <button key={c} onClick={() => setCategory(c)}
                    className={`text-[12px] px-3 py-1 rounded-full border transition-colors ${
                      c === category
                        ? "bg-navy-900 text-white border-navy-900"
                        : "bg-card text-ink-muted border-line hover:border-navy-700"}`}>
                    {c}
                  </button>
                ))}
              </div>
            </div>
            {forecast === null ? (
              <div className="p-10 flex justify-center"><Spinner /></div>
            ) : points.length === 0 ? (
              <p className="p-6 text-sm text-ink-muted">
                No forecasts yet — run the backtest (admin: “Refresh forecasts”).
              </p>
            ) : (
              <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_260px] items-start">
                <Suspense fallback={<div className="h-[320px] flex items-center justify-center"><Spinner /></div>}>
                  <ForecastChart points={points} />
                </Suspense>
                {backtest && (
                  <div>
                    <p className="text-[11px] font-semibold tracking-[0.18em] text-ink-muted uppercase font-display">
                      Backtest : mean absolute error
                    </p>
                    <div className="mt-1 space-y-1">
                      {Object.entries(backtest).sort((a, b) => a[1].mae - b[1].mae).map(([name, m]) => (
                        <div key={name} className="flex items-center justify-between text-[13px]">
                          <span className={name === bestAlgo ? "font-semibold text-navy-900" : "text-ink-muted"}>
                            {name.replace(/_/g, " ")}
                            {name === bestAlgo && (
                              <span className="ml-1.5 text-[10px] uppercase tracking-wider text-ok">winner</span>
                            )}
                          </span>
                          <span className="font-mono">{Number(m.mae).toFixed(3)}</span>
                        </div>
                      ))}
                    </div>
                    <p className="text-[11px] text-ink-muted mt-3 leading-relaxed">
                      Each of the last 9 months is predicted by models fit only on
                      strictly earlier data, the honest evaluation for time series.
                    </p>
                  </div>
                )}
              </div>
            )}
          </Card>
        </section>
      </div>
    </main>
  );
}
