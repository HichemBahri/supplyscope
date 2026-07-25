/** Renders a validated chart spec + rows with Plotly (ADR-003 dispatcher).
 *  KPI and table are custom; bar/line/pie/scatter go through Plotly with
 *  animated transitions so live refreshes feel organic, not snappy. */
import { useEffect, useRef, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
// @ts-expect-error no types shipped for the basic dist bundle
import Plotly from "plotly.js-basic-dist-min";
import type { ChartSpec } from "../lib/types";

const Plot = createPlotlyComponent(Plotly);

const SERIES = ["#155e97", "#4d8ec4", "#0b2239", "#88a9c3", "#f2620f", "#5b6b7c"];
const FONT = { family: "Inter, sans-serif", color: "#17202b", size: 12 };

interface Props {
  spec: ChartSpec;
  columns: string[];
  rows: unknown[][];
  height?: number;
}

function col(columns: string[], rows: unknown[][], field?: string): unknown[] {
  if (!field) return [];
  const i = columns.indexOf(field);
  return i === -1 ? [] : rows.map((r) => r[i]);
}

export function ChartRenderer({ spec, columns, rows, height = 300 }: Props) {
  if (spec.chart_type === "kpi") return <Kpi spec={spec} columns={columns} rows={rows} />;
  if (spec.chart_type === "table") return <DataTable columns={columns} rows={rows} />;

  const data: object[] = [];
  if (spec.chart_type === "bar") {
    for (const [i, y] of (spec.y_fields ?? []).entries()) {
      const horizontal = spec.orientation === "h";
      data.push({
        type: "bar", name: y,
        x: horizontal ? col(columns, rows, y) : col(columns, rows, spec.x_field),
        y: horizontal ? col(columns, rows, spec.x_field) : col(columns, rows, y),
        orientation: spec.orientation ?? "v",
        marker: { color: SERIES[i % SERIES.length] },
      });
    }
  } else if (spec.chart_type === "line") {
    for (const [i, y] of (spec.y_fields ?? []).entries()) {
      data.push({
        type: "scatter", mode: "lines+markers", name: y,
        x: col(columns, rows, spec.x_field), y: col(columns, rows, y),
        line: { color: SERIES[i % SERIES.length], width: 2.5 },
        marker: { size: 5 },
      });
    }
  } else if (spec.chart_type === "pie") {
    data.push({
      type: "pie",
      labels: col(columns, rows, spec.label_field),
      values: col(columns, rows, spec.value_field),
      hole: 0.45,
      marker: { colors: SERIES },
      textinfo: "label+percent",
    });
  } else if (spec.chart_type === "scatter") {
    data.push({
      type: "scatter", mode: "markers",
      x: col(columns, rows, spec.x_field), y: col(columns, rows, spec.y_field),
      marker: { size: 8, color: "#155e97", opacity: 0.75 },
    });
  }

  return (
    <Plot
      data={data as never}
      layout={{
        height,
        margin: { l: 56, r: 16, t: 8, b: 44 },
        font: FONT,
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        colorway: SERIES,
        barmode: spec.stacked ? "stack" : "group",
        showlegend: (spec.y_fields?.length ?? 0) > 1 || spec.chart_type === "pie",
        legend: { orientation: "h", y: -0.2 },
        xaxis: { gridcolor: "#eef1f5", zerolinecolor: "#e2e8f0", automargin: true },
        yaxis: { gridcolor: "#eef1f5", zerolinecolor: "#e2e8f0", automargin: true },
        transition: { duration: 450, easing: "cubic-in-out" },
      } as never}
      config={{ displayModeBar: false, responsive: true } as never}
      style={{ width: "100%" }}
      useResizeHandler
    />
  );
}

function Kpi({ spec, columns, rows }: { spec: ChartSpec; columns: string[]; rows: unknown[][] }) {
  const raw = col(columns, rows, spec.value_field)[0];
  const target = typeof raw === "number" ? raw : Number(raw ?? 0);
  const [display, setDisplay] = useState(target);
  const prev = useRef(target);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(target); prev.current = target; return;
    }
    const from = prev.current; prev.current = target;
    const t0 = performance.now(); const dur = 600;
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      setDisplay(from + (target - from) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  const formatted = Number.isInteger(target)
    ? Math.round(display).toLocaleString("en-US")
    : display.toLocaleString("en-US", { maximumFractionDigits: 2 });

  return (
    <div className="flex flex-col items-start gap-1 py-6">
      <span className="font-display text-5xl font-bold text-navy-900 tabular-nums">
        {formatted}
        {spec.unit && <span className="ml-2 text-xl text-ink-muted font-sans font-medium">{spec.unit}</span>}
      </span>
    </div>
  );
}

function DataTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-line">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-canvas">
          <tr>
            {columns.map((c) => (
              <th key={c} className="eyebrow px-3 py-2 text-left font-medium">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono text-[13px]">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line/70">
              {r.map((v, j) => (
                <td key={j} className="px-3 py-1.5 whitespace-nowrap">
                  {v === null ? <span className="text-ink-muted">NULL</span> : String(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
