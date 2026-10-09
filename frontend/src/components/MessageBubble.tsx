import { useState } from "react";
import { ChevronDown, Database, Pin, RotateCcw } from "lucide-react";
import { clsx } from "clsx";
import { useAuth } from "../lib/auth";
import type { Message } from "../lib/types";
import { LazyChart } from "./LazyChart";
import { Button } from "./ui/Button";

interface Props {
  message: Message;
  onPin?: (m: Message) => void;
}

export function MessageBubble({ message, onPin }: Props) {
  const [showSql, setShowSql] = useState(false);
  const [showAttempts, setShowAttempts] = useState(false);
  const isUser = message.role === "user";
  const meta = message.result_meta;
  // Any validated spec is pinnable — tables included: a saved table lives on
  // dashboards and refreshes reactively exactly like a graphical chart.
  const { user } = useAuth();
  // any validated spec is pinnable — but pinning is a PRODUCER action:
  // managers consume shared dashboards, they don't build them (Phase 9)
  const canPin = user?.role !== "manager";
  const hasChart = !!message.chart && !!meta && !meta.failed && canPin;

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-lg rounded-br-sm bg-navy-900 px-4 py-2.5 text-sm text-white">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%] rounded-lg rounded-bl-sm border border-line bg-card">
        <div className="px-4 pt-3.5 text-sm leading-relaxed whitespace-pre-wrap">{message.content}</div>

        {meta && !meta.failed && message.chart && (
          <div className="px-4 pt-3">
            <LazyChart
              spec={message.chart}
              columns={meta.columns}
              rows={meta.preview_rows}
              height={280}
            />
          </div>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line px-4 py-2.5">
          {meta && (
            <span className="eyebrow">
              {meta.failed
                ? `failed after ${meta.attempts.length} attempt(s)`
                : `${meta.row_count} row${meta.row_count > 1 ? "s" : ""} · ${meta.duration_ms} ms` +
                  (meta.attempts.length ? ` · self-corrected ×${meta.attempts.length}` : "")}
            </span>
          )}
          {message.sql_query && (
            <button
              onClick={() => setShowSql(!showSql)}
              className="flex items-center gap-1.5 text-[13px] font-medium text-action hover:text-action-strong"
            >
              <Database className="size-3.5" />
              SQL
              <ChevronDown className={clsx("size-3.5 transition-transform", showSql && "rotate-180")} />
            </button>
          )}
          {meta?.attempts.length ? (
            <button
              onClick={() => setShowAttempts(!showAttempts)}
              className="flex items-center gap-1.5 text-[13px] font-medium text-action hover:text-action-strong"
              title="Show the failed attempts and the database errors the agent corrected"
            >
              <RotateCcw className="size-3.5" />
              self-correction ×{meta.attempts.length}
              <ChevronDown className={clsx("size-3.5 transition-transform", showAttempts && "rotate-180")} />
            </button>
          ) : null}
          {hasChart && onPin && (
            <Button variant="ghost" className="ml-auto !px-2.5 !py-1 text-[13px]"
                    onClick={() => onPin(message)}>
              <Pin className="size-3.5" /> Pin to dashboard
            </Button>
          )}
        </div>

        {showAttempts && meta?.attempts.length ? (
          <div className="border-t border-line bg-canvas px-4 py-3 text-[12.5px]">
            {meta.attempts.map((a, i) => (
              <div key={i} className={clsx(i > 0 && "mt-3 border-t border-line pt-3")}>
                <div className="eyebrow">attempt {i + 1} · rejected</div>
                <pre className="mt-1 overflow-x-auto rounded bg-navy-900 px-3 py-2 font-mono text-white/90">{a.sql}</pre>
                <div className="mt-1 font-mono text-danger">{a.error}</div>
              </div>
            ))}
            <div className="eyebrow mt-3">attempt {meta.attempts.length + 1} · accepted (see SQL)</div>
          </div>
        ) : null}

        {showSql && message.sql_query && (
          <pre className="overflow-x-auto border-t border-line bg-navy-900 px-4 py-3 font-mono text-[12.5px] leading-relaxed text-white/90">
            {message.sql_query}
          </pre>
        )}
      </div>
    </div>
  );
}
