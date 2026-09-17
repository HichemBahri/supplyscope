/** SSE subscription to /api/charts/stream — the reactive heartbeat of the UI. */
import { useEffect, useRef, useState } from "react";
import { useAuth } from "./auth";
import type { ChartUpdateEvent, Comment } from "./types";

export type StreamStatus = "connecting" | "live" | "offline";

export function useChartStream(
  onUpdate: (e: ChartUpdateEvent) => void,
  onComment?: (c: Comment) => void,
) {
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [lastTables, setLastTables] = useState<string[]>([]);
  const handler = useRef(onUpdate);
  handler.current = onUpdate;
  const commentHandler = useRef(onComment);
  commentHandler.current = onComment;

  const { token } = useAuth();
  useEffect(() => {
    // token-reactive: connect when a token exists, reconnect when it
    // changes, disconnect on logout. An empty-deps one-shot here dies
    // forever if the component mounts before login.
    if (!token) return;
    const es = new EventSource(`/api/charts/stream?token=${encodeURIComponent(token)}`);
    es.addEventListener("connected", () => setStatus("live"));
    es.addEventListener("chart_update", (ev) => {
      const payload = JSON.parse((ev as MessageEvent).data) as ChartUpdateEvent;
      setLastTables(payload.source_tables);
      handler.current(payload);
    });
    es.addEventListener("comment_added", (ev) => {
      const c = JSON.parse((ev as MessageEvent).data) as Comment;
      commentHandler.current?.(c);
    });
    es.addEventListener("alerts_changed", (ev) => {
      const s = JSON.parse((ev as MessageEvent).data);
      // window-level broadcast: the sidebar badge listens from anywhere
      window.dispatchEvent(new CustomEvent("ss-alerts", { detail: s }));
    });
    es.onerror = () => setStatus("offline"); // EventSource auto-reconnects
    return () => es.close();
  }, [token]);

  return { status, lastTables };
}
