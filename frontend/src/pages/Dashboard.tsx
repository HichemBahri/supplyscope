import { useCallback, useEffect, useState } from "react";
import { Trash2, RefreshCw } from "lucide-react";
import { clsx } from "clsx";
import { api } from "../lib/api";
import { useChartStream } from "../lib/useChartStream";
import type { ChartData, ChartUpdateEvent, SavedChart } from "../lib/types";
import { LazyChart } from "../components/LazyChart";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

interface Slot {
  chart: SavedChart;
  data?: ChartData;
  refreshedAt?: string;
  flash: boolean;
}

export default function Dashboard() {
  const [slots, setSlots] = useState<Record<number, Slot>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const charts = await api.charts();
    const next: Record<number, Slot> = {};
    for (const c of charts) next[c.chart_id] = { chart: c, flash: false };
    setSlots(next);
    setLoading(false);
    // hydrate data in parallel
    charts.forEach(async (c) => {
      try {
        const data = await api.chartData(c.chart_id);
        setSlots((s) => s[c.chart_id] ? { ...s, [c.chart_id]: { ...s[c.chart_id], data } } : s);
      } catch { /* chart may fail to run; card shows error state */ }
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  const onUpdate = useCallback((e: ChartUpdateEvent) => {
    setSlots((s) => {
      const slot = s[e.chart_id];
      if (!slot) return s;
      return {
        ...s,
        [e.chart_id]: {
          ...slot,
          data: e,
          refreshedAt: e.refreshed_at,
          flash: true,
        },
      };
    });
    setTimeout(() => {
      setSlots((s) => s[e.chart_id] ? { ...s, [e.chart_id]: { ...s[e.chart_id], flash: false } } : s);
    }, 1300);
  }, []);

  const { status, lastTables } = useChartStream(onUpdate);

  const remove = async (id: number) => {
    await api.deleteChart(id);
    setSlots((s) => { const n = { ...s }; delete n[id]; return n; });
  };

  const list = Object.values(slots);

  return (
    <div className="flex h-screen flex-1 flex-col overflow-hidden">
      {/* telemetry strip — the signature */}
      <div className="flex items-center gap-4 border-b border-line bg-card px-6 py-3">
        <h1 className="font-display text-lg font-bold text-navy-900">Dashboard</h1>
        <div className="ml-auto flex items-center gap-2.5">
          {status === "live" ? (
            <>
              <span className="pulse-dot" aria-hidden />
              <span className="eyebrow !text-signal">live stream active</span>
            </>
          ) : status === "connecting" ? (
            <span className="eyebrow">connecting to stream…</span>
          ) : (
            <span className="eyebrow !text-danger">stream lost — reconnecting…</span>
          )}
          {lastTables.length > 0 && (
            <span className="eyebrow hidden sm:inline">
              · last change: {lastTables.join(", ")}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="grid h-40 place-items-center"><Spinner className="size-6" /></div>
        ) : list.length === 0 ? (
          <div className="mt-20 text-center">
            <h2 className="font-display text-xl font-bold text-navy-900">No pinned charts yet</h2>
            <p className="mx-auto mt-2 max-w-md text-sm text-ink-muted">
              Pin a chart from the Assistant: it will appear here and refresh itself
              whenever the ERP data changes.
            </p>
          </div>
        ) : (
          <div className="grid gap-5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))" }}>
            {list.map(({ chart, data, refreshedAt, flash }) => (
              <Card key={chart.chart_id}
                    className={clsx("flex flex-col p-4 transition-shadow", flash && "flash-update")}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-[15px] font-bold text-navy-900">{chart.title}</h3>
                    <div className="eyebrow mt-0.5">
                      {data ? `${data.row_count} row${data.row_count > 1 ? "s" : ""}` : "loading"}
                      {refreshedAt && (
                        <span className="text-signal">
                          {" "}· refreshed {new Date(refreshedAt).toLocaleTimeString("en-GB")}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <button title="Refresh"
                            onClick={async () => {
                              const d = await api.chartData(chart.chart_id);
                              setSlots((s) => ({ ...s, [chart.chart_id]: { ...s[chart.chart_id], data: d } }));
                            }}
                            className="rounded p-1.5 text-ink-muted hover:bg-line/60 hover:text-ink">
                      <RefreshCw className="size-4" />
                    </button>
                    <button title="Remove" onClick={() => remove(chart.chart_id)}
                            className="rounded p-1.5 text-ink-muted hover:bg-danger/10 hover:text-danger">
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </div>
                <div className="mt-2 min-h-[220px]">
                  {data ? (
                    <LazyChart spec={data.chart_spec} columns={data.columns}
                                   rows={data.rows} height={260} />
                  ) : (
                    <div className="grid h-52 place-items-center"><Spinner className="size-5" /></div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
