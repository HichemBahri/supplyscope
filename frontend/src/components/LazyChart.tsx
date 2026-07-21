/** Code-split chart renderer: Plotly (~1.3 MB) loads only when the first
 *  chart is actually rendered, keeping the app shell instant. */
import { Suspense, lazy, type ComponentProps } from "react";
import { Spinner } from "./ui/Spinner";

const Inner = lazy(() =>
  import("./ChartRenderer").then((m) => ({ default: m.ChartRenderer })),
);

export function LazyChart(props: ComponentProps<typeof Inner>) {
  return (
    <Suspense fallback={<div className="grid h-52 place-items-center"><Spinner className="size-5" /></div>}>
      <Inner {...props} />
    </Suspense>
  );
}
