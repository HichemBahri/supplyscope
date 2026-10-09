/** Dashboards home: my boards + boards shared with the whole team. */
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Globe2, Lock, Plus } from "lucide-react";
import { useRef } from "react";
import { Trash2, Wand2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { DashboardSummary } from "../lib/types";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

export default function Dashboards() {
  const { user } = useAuth();
  const [topic, setTopic] = useState("");
  const [synth, setSynth] = useState<null | { stage: string; secs: number }>(null);
  const [report, setReport] = useState<Awaited<ReturnType<typeof api.synthesizeDashboard>> | null>(null);
  const tick = useRef<number | null>(null);

  const removeBoard = async (id: number, e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    if (!window.confirm("Delete this dashboard? Its pinned charts survive."))
      return;
    try {
      await api.deleteDashboard(id);
    } catch (err) {
      window.alert(err instanceof ApiError ? `Could not delete: ${err.message}` : "Could not delete this dashboard.");
    }
    load();
  };

  const generate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (topic.trim().length < 3 || synth) return;
    setReport(null);
    let secs = 0;
    setSynth({ stage: "Planning complementary views…", secs });
    tick.current = window.setInterval(() => {
      secs += 1;
      setSynth({ stage: secs < 4 ? "Planning complementary views…"
        : "Generating and validating SQL for each view…", secs });
    }, 1000);
    try {
      const out = await api.synthesizeDashboard(topic.trim());
      setReport(out);
      setTopic("");
      load();                                  // refresh the dashboard list
    } finally {
      if (tick.current) window.clearInterval(tick.current);
      setSynth(null);
    }
  };
  const [boards, setBoards] = useState<DashboardSummary[] | null>(null);
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => api.dashboards().then(setBoards).catch(() => setBoards([]));
  useEffect(() => { load(); }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (title.trim().length < 3) return;
    setCreating(true);
    try { await api.createDashboard(title.trim()); setTitle(""); load(); }
    finally { setCreating(false); }
  };

  const mine = boards?.filter((b) => b.owner_id === user?.user_id) ?? [];
  const shared = boards?.filter((b) => b.owner_id !== user?.user_id) ?? [];

  const BoardCard = ({ b }: { b: DashboardSummary }) => (
    <Link to={`/dashboard/${b.dashboard_id}`}>
      <Card className="p-4 transition-colors hover:border-action/50">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-display text-[15px] font-bold text-navy-900">{b.title}</h3>
                {(user?.role === "admin" || b.owner_id === user?.user_id) && (
                  <button onClick={(e) => removeBoard(b.dashboard_id, e)}
                    className="ml-auto shrink-0 text-ink-muted hover:text-danger"
                    title="Delete dashboard">
                    <Trash2 className="size-4" />
                  </button>
                )}
          {b.is_shared ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-action/10 px-2 py-0.5 text-[11px] font-medium text-action">
              <Globe2 className="size-3" /> Team
            </span>
          ) : (
            <Lock className="size-3.5 text-ink-muted" />
          )}
        </div>
        <div className="eyebrow mt-2">
          {b.chart_count} chart{b.chart_count !== 1 ? "s" : ""}
          {b.owner_id !== user?.user_id &&
            ` · by ${b.owner_first_name} ${b.owner_last_name}`}
        </div>
      </Card>
    </Link>
  );

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display text-xl font-bold text-navy-900">Dashboards</h1>
          {user?.role !== "manager" && (
          <form onSubmit={generate} className="w-full mb-4">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Wand2 className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
                <input value={topic} onChange={(e) => setTopic(e.target.value)}
                  disabled={!!synth}
                  placeholder='Generate a dashboard from a topic. Example: "supplier performance", "project cost control"'
                  className="w-full rounded-lg border border-line bg-card pl-9 pr-3 py-2 text-sm" />
              </div>
              <button type="submit" disabled={!!synth || topic.trim().length < 3}
                className="rounded-lg bg-action text-white text-sm px-4 py-2 disabled:opacity-50">
                {synth ? `${synth.secs}s…` : "Generate"}
              </button>
            </div>
            {synth && (
              <p className="text-[12px] text-ink-muted mt-2 animate-pulse">
                {synth.stage} The agent plans, writes, executes and validates
                each query through the same read-only path as chat.
              </p>
            )}
            {report && (
              <div className="mt-2 text-[12px] rounded-lg border border-line bg-card px-3 py-2">
                <span className="font-semibold text-navy-900">
                  “{report.title}” created
                </span>{" "}
                — {report.created.length}/{report.planned} views built
                {report.failed.length > 0 && (
                  <span className="text-warn"> · {report.failed.length} dropped
                    by the quality gates</span>
                )}
                {report.failed.length > 0 && (
                  <ul className="mt-2 space-y-1 border-t border-line pt-2">
                    {report.failed.map((f) => (
                      <li key={f.question} className="text-ink-muted">
                        <span className="text-ink">{f.question}</span>
                        <span className="block text-[11px] text-warn">{f.reason}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </form>
          )}
          {user?.role !== "manager" && (
          <form onSubmit={create} className="ml-auto flex items-center gap-2">
            <Input className="!w-64" placeholder="New dashboard title…"
                   value={title} onChange={(e) => setTitle(e.target.value)} />
            <Button disabled={creating || title.trim().length < 3}>
              <Plus className="size-4" /> Create
            </Button>
          </form>
          )}
        </div>

        {boards === null ? (
          <div className="grid h-40 place-items-center"><Spinner className="size-6" /></div>
        ) : (
          <>
            <h2 className="eyebrow mt-6">My dashboards</h2>
            {mine.length === 0 ? (
              <p className="mt-2 text-sm text-ink-muted">
                Create a dashboard above, then add charts to it from its page.
              </p>
            ) : (
              <div className="mt-2 grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
                {mine.map((b) => <BoardCard key={b.dashboard_id} b={b} />)}
              </div>
            )}
            <h2 className="eyebrow mt-8">Shared with the team</h2>
            {shared.length === 0 ? (
              <p className="mt-2 text-sm text-ink-muted">Nothing shared yet.</p>
            ) : (
              <div className="mt-2 grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
                {shared.map((b) => <BoardCard key={b.dashboard_id} b={b} />)}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
