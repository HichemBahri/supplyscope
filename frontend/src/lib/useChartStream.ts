/** SSE subscription to /api/charts/stream — the reactive heartbeat of the UI. */
import { useEffect, useRef, useState } from "react";
import { getToken } from "./api";
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

  useEffect(() => {
    const token = getToken();
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
    es.onerror = () => setStatus("offline"); // EventSource auto-reconnects
    return () => es.close();
  }, []);

  return { status, lastTables };
}
