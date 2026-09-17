/** Global alert toasts — rides the SAME SSE event the sidebar badge uses.
 *  When an evaluation reports new alerts, a toast pops anywhere in the app:
 *  no polling, no page-specific wiring — the reactivity spine doing one
 *  more job. Click-through lands on the Alerts page. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BellRing, ShieldAlert } from "lucide-react";
import { useChartStream } from "../lib/useChartStream";

interface Toast {
  id: number;
  text: string;
  critical: boolean;
}

export default function ToastHost() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nav = useNavigate();
  // ToastHost OWNS an SSE connection: alerts must reach the user on every
  // page, not only the ones that happen to render live charts.
  useChartStream(() => {});

  useEffect(() => {
    const h = (ev: Event) => {
      const s = (ev as CustomEvent).detail ?? {};
      // notify on RAISED (new + reactivated), not just first-ever inserts:
      // a recurring condition must announce itself every time it returns
      const n = s.raised ?? s.new ?? 0;
      if (n <= 0) return;
      const crit = s.new_critical ?? 0;
      const t: Toast = {
        id: Date.now() + Math.random(),
        text:
          `${n} new alert${n > 1 ? "s" : ""}` +
          (crit > 0 ? ` — ${crit} critical` : ""),
        critical: crit > 0,
      };
      setToasts((ts) => [...ts.slice(-3), t]);
      window.setTimeout(
        () => setToasts((ts) => ts.filter((x) => x.id !== t.id)), 6000);
    };
    window.addEventListener("ss-alerts", h);
    return () => window.removeEventListener("ss-alerts", h);
  }, []);

  if (toasts.length === 0) return null;
  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <button key={t.id}
          onClick={() => { setToasts([]); nav("/alerts"); }}
          className={`flex items-center gap-2.5 rounded-lg border bg-card px-4 py-3
            shadow-lg text-left text-[13px] font-medium transition-transform
            hover:-translate-y-0.5 ${t.critical
              ? "border-danger/40 text-danger"
              : "border-line text-navy-900"}`}>
          {t.critical
            ? <ShieldAlert className="size-4 shrink-0" />
            : <BellRing className="size-4 shrink-0" />}
          {t.text}
          <span className="text-[11px] text-ink-muted font-normal ml-1">
            view →
          </span>
        </button>
      ))}
    </div>
  );
}
