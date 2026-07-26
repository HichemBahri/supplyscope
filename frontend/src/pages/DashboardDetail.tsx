/** One dashboard: live reactive chart grid + team comments (live too).
 *  Owners curate charts; admins publish to the whole team. */
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Globe2, MessageSquareText, Plus, RefreshCw, SendHorizonal, Trash2, X,
} from "lucide-react";
import { clsx } from "clsx";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useChartStream } from "../lib/useChartStream";
import type {
  ChartData, ChartUpdateEvent, Comment, DashboardDetail as Detail, SavedChart,
} from "../lib/types";
import { LazyChart } from "../components/LazyChart";
import { Avatar } from "../components/Avatar";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

interface Slot { data?: ChartData; refreshedAt?: string; flash: boolean }

export default function DashboardDetail() {
  const { id } = useParams();
  const dashboardId = Number(id);
  const nav = useNavigate();
  const { user } = useAuth();

  const [board, setBoard] = useState<Detail | null>(null);
  const [slots, setSlots] = useState<Record<number, Slot>>({});
  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");
  const [showPicker, setShowPicker] = useState(false);
  const [myCharts, setMyCharts] = useState<SavedChart[]>([]);
  const [error, setError] = useState("");
  const commentsEnd = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.dashboard(dashboardId);
      setBoard(d);
      d.charts.forEach(async (c) => {
        try {
          const data = await api.chartData(c.chart_id);
          setSlots((s) => ({ ...s, [c.chart_id]: { ...(s[c.chart_id] ?? { flash: false }), data } }));
        } catch { /* card shows loading state */ }
      });
      setComments(await api.comments(dashboardId));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) nav("/dashboard");
    }
  }, [dashboardId, nav]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { commentsEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [comments]);

  const onUpdate = useCallback((e: ChartUpdateEvent) => {
    setSlots((s) => s[e.chart_id] === undefined && !board?.charts.some(c => c.chart_id === e.chart_id)
      ? s
      : { ...s, [e.chart_id]: { data: e, refreshedAt: e.refreshed_at, flash: true } });
    setTimeout(() => setSlots((s) => s[e.chart_id]
      ? { ...s, [e.chart_id]: { ...s[e.chart_id], flash: false } } : s), 1300);
  }, [board]);

  const onComment = useCallback((c: Comment) => {
    if (c.dashboard_id !== dashboardId) return;
    setComments((prev) => prev.some((x) => x.comment_id === c.comment_id) ? prev : [...prev, c]);
  }, [dashboardId]);

  const { status } = useChartStream(onUpdate, onComment);

  const postComment = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    try {
      const c = await api.postComment(dashboardId, text);
      setComments((prev) => prev.some((x) => x.comment_id === c.comment_id) ? prev : [...prev, c]);
    } catch { setError("Could not post the comment."); }
  };

  const openPicker = async () => {
    setMyCharts(await api.charts());
    setShowPicker(true);
  };

  const addChart = async (chartId: number) => {
    await api.addChartToDashboard(dashboardId, chartId);
    setShowPicker(false);
    load();
  };

  const removeChart = async (chartId: number) => {
    await api.removeChartFromDashboard(dashboardId, chartId);
    setSlots((s) => { const n = { ...s }; delete n[chartId]; return n; });
    load();
  };

  const toggleShare = async () => {
    if (!board) return;
    try {
      await api.updateDashboard(dashboardId, { is_shared: !board.is_shared });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Update failed.");
    }
  };

  if (!board) return <div className="grid flex-1 place-items-center"><Spinner className="size-6" /></div>;

  const isAdminOwner = board.can_edit && user?.role === "admin";
  const onBoard = new Set(board.charts.map((c) => c.chart_id));

  return (
    <div className="flex h-screen flex-1 overflow-hidden">
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* telemetry strip */}
        <div className="flex flex-wrap items-center gap-3 border-b border-line bg-card px-6 py-3">
          <Link to="/dashboard" className="rounded p-1.5 text-ink-muted hover:bg-line/60">
            <ArrowLeft className="size-4.5" />
          </Link>
          <h1 className="font-display text-lg font-bold text-navy-900">{board.title}</h1>
          {board.is_shared && (
            <span className="inline-flex items-center gap-1 rounded-full bg-action/10 px-2 py-0.5 text-[11px] font-medium text-action">
              <Globe2 className="size-3" /> Shared with the team
            </span>
          )}
          {!board.can_edit && (
            <span className="eyebrow">by {board.owner_first_name} {board.owner_last_name}</span>
          )}
          <div className="ml-auto flex items-center gap-2.5">
            {status === "live" ? (
              <><span className="pulse-dot" aria-hidden />
                <span className="eyebrow !text-signal">live stream active</span></>
            ) : (
              <span className="eyebrow">connecting…</span>
            )}
            {isAdminOwner && (
              <Button variant={board.is_shared ? "ghost" : "navy"} className="!py-1.5 text-[13px]"
                      onClick={toggleShare}>
                {board.is_shared ? "Unshare" : "Share with team"}
              </Button>
            )}
            {board.can_edit && (
              <Button variant="ghost" className="!py-1.5 text-[13px]" onClick={openPicker}>
                <Plus className="size-4" /> Add chart
              </Button>
            )}
          </div>
        </div>
        {error && <p className="px-6 pt-2 text-sm text-danger">{error}</p>}

        <div className="flex-1 overflow-y-auto p-6">
          {board.charts.length === 0 ? (
            <div className="mt-20 text-center">
              <h2 className="font-display text-xl font-bold text-navy-900">Empty dashboard</h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-ink-muted">
                {board.can_edit
                  ? "Add charts you pinned from the Assistant — they will refresh live here."
                  : "The owner has not added charts yet."}
              </p>
            </div>
          ) : (
            <div className="grid gap-5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))" }}>
              {board.charts.map((c) => {
                const slot = slots[c.chart_id];
                return (
                  <Card key={c.chart_id}
                        className={clsx("flex flex-col p-4 transition-shadow", slot?.flash && "flash-update")}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-display text-[15px] font-bold text-navy-900">{c.title}</h3>
                        <div className="eyebrow mt-0.5">
                          {slot?.data ? `${slot.data.row_count} row${slot.data.row_count > 1 ? "s" : ""}` : "loading"}
                          {slot?.refreshedAt && (
                            <span className="text-signal">
                              {" "}· refreshed {new Date(slot.refreshedAt).toLocaleTimeString("en-GB")}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <button title="Refresh"
                                onClick={async () => {
                                  const d = await api.chartData(c.chart_id);
                                  setSlots((s) => ({ ...s, [c.chart_id]: { ...(s[c.chart_id] ?? { flash: false }), data: d } }));
                                }}
                                className="rounded p-1.5 text-ink-muted hover:bg-line/60 hover:text-ink">
                          <RefreshCw className="size-4" />
                        </button>
                        {board.can_edit && (
                          <button title="Remove from dashboard" onClick={() => removeChart(c.chart_id)}
                                  className="rounded p-1.5 text-ink-muted hover:bg-danger/10 hover:text-danger">
                            <Trash2 className="size-4" />
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 min-h-[220px]">
                      {slot?.data ? (
                        <LazyChart spec={slot.data.chart_spec} columns={slot.data.columns}
                                   rows={slot.data.rows} height={260} />
                      ) : (
                        <div className="grid h-52 place-items-center"><Spinner className="size-5" /></div>
                      )}
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* comments rail */}
      <aside className="flex w-80 shrink-0 flex-col border-l border-line bg-card">
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          <MessageSquareText className="size-4 text-ink-muted" />
          <span className="font-display text-sm font-bold text-navy-900">Team discussion</span>
          <span className="eyebrow ml-auto">{comments.length}</span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {comments.length === 0 ? (
            <p className="mt-6 text-center text-sm text-ink-muted">
              No comments yet — start the discussion.
            </p>
          ) : comments.map((c) => (
            <div key={c.comment_id} className="mb-3 flex gap-2.5">
              <Avatar user={c} size={28} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-[13px] font-medium text-ink">
                    {c.first_name} {c.last_name}
                  </span>
                  <span className="text-[11px] text-ink-muted">
                    {new Date(c.created_at).toLocaleTimeString("en-GB",
                      { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  {(c.user_id === user?.user_id || user?.role === "admin") && (
                    <button
                      onClick={async () => {
                        await api.deleteComment(c.comment_id);
                        setComments((p) => p.filter((x) => x.comment_id !== c.comment_id));
                      }}
                      className="ml-auto text-ink-muted/60 hover:text-danger" title="Delete">
                      <X className="size-3.5" />
                    </button>
                  )}
                </div>
                <p className="text-[13px] leading-relaxed text-ink">{c.content}</p>
              </div>
            </div>
          ))}
          <div ref={commentsEnd} />
        </div>
        <form onSubmit={postComment} className="flex items-center gap-2 border-t border-line p-3">
          <input
            value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Write a comment…"
            className="flex-1 rounded-md border border-line bg-canvas px-3 py-2 text-sm focus:border-action focus:outline-none focus:ring-2 focus:ring-action/20"
          />
          <Button disabled={!draft.trim()} className="!px-2.5">
            <SendHorizonal className="size-4" />
          </Button>
        </form>
      </aside>

      {/* add-chart picker */}
      {showPicker && (
        <div className="fixed inset-0 z-10 grid place-items-center bg-navy-900/40 p-4"
             onClick={() => setShowPicker(false)}>
          <Card className="max-h-[70vh] w-[440px] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-lg font-bold text-navy-900">Add a chart</h3>
            <p className="mt-1 text-sm text-ink-muted">Charts you pinned from the Assistant.</p>
            <div className="mt-3 flex flex-col gap-2">
              {myCharts.filter((c) => !onBoard.has(c.chart_id)).map((c) => (
                <button key={c.chart_id} onClick={() => addChart(c.chart_id)}
                        className="rounded-md border border-line px-3 py-2.5 text-left text-sm transition-colors hover:border-action/50 hover:bg-action/5">
                  <span className="font-medium text-ink">{c.title}</span>
                  <span className="eyebrow ml-2">{c.chart_spec.chart_type}</span>
                </button>
              ))}
              {myCharts.filter((c) => !onBoard.has(c.chart_id)).length === 0 && (
                <p className="text-sm text-ink-muted">
                  Nothing left to add — pin more charts from the Assistant first.
                </p>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
