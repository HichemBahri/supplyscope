/** Admin-only audit trail: who did what, when. Read-only view over
 *  GET /api/admin/audit (logins, lockouts, role changes, deletions,
 *  alert acknowledgements, recommendation decisions). */
import { useEffect, useState } from "react";
import { ScrollText, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import type { AuditEntry } from "../lib/types";

const ACTIONS = [
  "", "login.success", "login.failed", "login.locked", "user.role_changed",
  "user.deleted", "alert.acknowledged", "reco.decision",
];

const TONE: Record<string, string> = {
  "login.failed": "bg-amber-100 text-amber-800",
  "login.locked": "bg-red-100 text-red-800",
  "user.deleted": "bg-red-100 text-red-800",
  "user.role_changed": "bg-blue-100 text-blue-800",
  "reco.decision": "bg-emerald-100 text-emerald-800",
};

function who(e: AuditEntry): string {
  if (e.first_name || e.last_name) return `${e.first_name ?? ""} ${e.last_name ?? ""}`.trim();
  if (e.email) return e.email;
  return e.user_id ? `user #${e.user_id}` : "system";
}

export default function Audit() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [action, setAction] = useState("");
  const [limit, setLimit] = useState(100);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api.adminAudit({ limit, action: action || undefined })
      .then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [action, limit]);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-wrap items-center gap-3">
          <ScrollText className="size-5 text-navy-900" />
          <h1 className="font-display text-xl font-bold text-navy-900">Audit trail</h1>
          <span className="eyebrow">{rows.length} entr{rows.length === 1 ? "y" : "ies"}</span>
          <div className="ml-auto flex items-center gap-2">
            <select value={action} onChange={(e) => setAction(e.target.value)}
                    className="rounded-md border border-line bg-card px-2 py-1.5 text-sm">
              {ACTIONS.map((a) => <option key={a} value={a}>{a || "all actions"}</option>)}
            </select>
            <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}
                    className="rounded-md border border-line bg-card px-2 py-1.5 text-sm">
              {[50, 100, 250, 500].map((n) => <option key={n} value={n}>last {n}</option>)}
            </select>
            <Button variant="ghost" onClick={load} disabled={loading} title="Refresh">
              <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
            </Button>
          </div>
        </div>
        <p className="mt-1 text-sm text-ink-muted">
          Every sensitive action is recorded with its actor, its detail and its time. Entries are never edited or deleted.
        </p>
        <Card className="mt-4 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-canvas">
              <tr>
                {["#", "When", "Who", "Action", "Detail"].map((h) => (
                  <th key={h} className="eyebrow px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.audit_id} className="border-t border-line align-top">
                  <td className="px-4 py-2.5 tabular-nums text-ink-muted">{e.audit_id}</td>
                  <td className="px-4 py-2.5 whitespace-nowrap tabular-nums">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="font-medium">{who(e)}</div>
                    {e.email && <div className="text-xs text-ink-muted">{e.email}</div>}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${TONE[e.action] ?? "bg-canvas text-navy-900"}`}>
                      {e.action}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <code className="text-xs text-ink-muted">{JSON.stringify(e.detail)}</code>
                  </td>
                </tr>
              ))}
              {!rows.length && !loading && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-ink-muted">No entries.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
