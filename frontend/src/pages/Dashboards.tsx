/** Dashboards home: my boards + boards shared with the whole team. */
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Globe2, Lock, Plus } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { DashboardSummary } from "../lib/types";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";

export default function Dashboards() {
  const { user } = useAuth();
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
          <form onSubmit={create} className="ml-auto flex items-center gap-2">
            <Input className="!w-64" placeholder="New dashboard title…"
                   value={title} onChange={(e) => setTitle(e.target.value)} />
            <Button disabled={creating || title.trim().length < 3}>
              <Plus className="size-4" /> Create
            </Button>
          </form>
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
