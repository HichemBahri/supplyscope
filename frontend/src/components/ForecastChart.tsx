/** Price-index forecast chart: observed history (solid) + model projection
 *  (dashed) with a "today" divider. Loaded lazily — Plotly is heavy. */
import createPlotlyComponent from "react-plotly.js/factory";
// @ts-expect-error no types shipped for the basic dist bundle
import Plotly from "plotly.js-basic-dist-min";
import type { ForecastPoint } from "../lib/types";

const Plot = createPlotlyComponent(Plotly);
const FONT = { family: "Inter, sans-serif", color: "#17202b", size: 12 };

export default function ForecastChart({ points }: { points: ForecastPoint[] }) {
  const history = points.filter((p) => p.kind === "history");
  const forecast = points.filter((p) => p.kind === "forecast");
  const lastHist = history[history.length - 1];
  // bridge the dashed line to the last observed point so there is no gap
  const fx = lastHist ? [lastHist.month, ...forecast.map((p) => p.month)] : forecast.map((p) => p.month);
  const fy = lastHist
    ? [Number(lastHist.price_index), ...forecast.map((p) => Number(p.price_index))]
    : forecast.map((p) => Number(p.price_index));

  return (
    <Plot
      data={[
        {
          type: "scatter", mode: "lines", name: "Observed index",
          x: history.map((p) => p.month),
          y: history.map((p) => Number(p.price_index)),
          line: { color: "#155e97", width: 2.5 },
        },
        {
          type: "scatter", mode: "lines+markers", name: "Model forecast",
          x: fx, y: fy,
          line: { color: "#0b2239", width: 2, dash: "dash" },
          marker: { size: 5 },
        },
      ]}
      layout={{
        autosize: true, height: 320, font: FONT,
        margin: { l: 48, r: 16, t: 8, b: 40 },
        paper_bgcolor: "transparent", plot_bgcolor: "transparent",
        xaxis: { gridcolor: "#e2e8f0" },
        yaxis: { gridcolor: "#e2e8f0", title: { text: "unit price / reference", font: { size: 11 } }, tickformat: ".2f" },
        legend: { orientation: "h", y: -0.18 },
        shapes: lastHist ? [{
          type: "line", x0: lastHist.month, x1: lastHist.month,
          y0: 0, y1: 1, yref: "paper",
          line: { color: "#5b6b7c", width: 1, dash: "dot" },
        }] : [],
        transition: { duration: 450, easing: "cubic-in-out" },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
      useResizeHandler
    />
  );
}
