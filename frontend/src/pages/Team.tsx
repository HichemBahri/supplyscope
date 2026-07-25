/** Admin-only employee management: full CRUD over accounts. */
import { useEffect, useState } from "react";
import { Pencil, Trash2, ShieldCheck, X, Check } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Avatar } from "../components/Avatar";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Card } from "../components/ui/Card";
import { DEPARTMENTS, type User } from "../lib/types";

export default function Team() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<Partial<User>>({});
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = () => api.adminUsers().then(setUsers).catch(() => {});
  useEffect(() => { load(); }, []);

  const startEdit = (u: User) => {
    setEditing(u.user_id);
    setDraft({ first_name: u.first_name, last_name: u.last_name,
               job_title: u.job_title, department: u.department, role: u.role });
    setError("");
  };

  const save = async (id: number) => {
    try {
      await api.adminUpdateUser(id, draft);
      setEditing(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Update failed.");
    }
  };

  const remove = async (id: number) => {
    try {
      await api.adminDeleteUser(id);
      setConfirmDelete(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed.");
      setConfirmDelete(null);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-xl font-bold text-navy-900">Team</h1>
          <span className="eyebrow">{users.length} registered employee{users.length !== 1 ? "s" : ""}</span>
        </div>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}
        <Card className="mt-4 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-canvas">
              <tr>
                {["Employee", "Job title", "Department", "Role", ""].map((h) => (
                  <th key={h} className="eyebrow px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id} className="border-t border-line">
                  {editing === u.user_id ? (
                    <>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <Avatar user={u} size={30} />
                          <div className="flex gap-1.5">
                            <Input className="!w-24" value={draft.first_name ?? ""}
                                   onChange={(e) => setDraft((d) => ({ ...d, first_name: e.target.value }))} />
                            <Input className="!w-24" value={draft.last_name ?? ""}
                                   onChange={(e) => setDraft((d) => ({ ...d, last_name: e.target.value }))} />
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <Input value={draft.job_title ?? ""}
                               onChange={(e) => setDraft((d) => ({ ...d, job_title: e.target.value }))} />
                      </td>
                      <td className="px-4 py-2.5">
                        <select value={draft.department}
                                onChange={(e) => setDraft((d) => ({ ...d, department: e.target.value }))}
                                className="rounded-md border border-line bg-card px-2 py-1.5 text-sm">
                          {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
                        </select>
                      </td>
                      <td className="px-4 py-2.5">
                        <select value={draft.role}
                                onChange={(e) => setDraft((d) => ({ ...d, role: e.target.value as User["role"] }))}
                                className="rounded-md border border-line bg-card px-2 py-1.5 text-sm">
                          <option value="analyst">Analyst</option>
                          <option value="admin">Administrator</option>
                        </select>
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex justify-end gap-1">
                          <button onClick={() => save(u.user_id)} title="Save"
                                  className="rounded p-1.5 text-ok hover:bg-ok/10"><Check className="size-4" /></button>
                          <button onClick={() => setEditing(null)} title="Cancel"
                                  className="rounded p-1.5 text-ink-muted hover:bg-line/60"><X className="size-4" /></button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <Avatar user={u} size={30} />
                          <div>
                            <div className="font-medium text-ink">
                              {u.first_name} {u.last_name}
                              {u.user_id === me?.user_id && <span className="ml-1.5 eyebrow">you</span>}
                            </div>
                            <div className="text-[12px] text-ink-muted">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5">{u.job_title}</td>
                      <td className="px-4 py-2.5">{u.department}</td>
                      <td className="px-4 py-2.5">
                        {u.role === "admin" ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-navy-900/8 px-2 py-0.5 text-[12px] font-medium text-navy-900">
                            <ShieldCheck className="size-3.5" /> Admin
                          </span>
                        ) : (
                          <span className="text-[12px] text-ink-muted">Analyst</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex justify-end gap-1">
                          <button onClick={() => startEdit(u)} title="Edit"
                                  className="rounded p-1.5 text-ink-muted hover:bg-line/60 hover:text-ink">
                            <Pencil className="size-4" />
                          </button>
                          {u.user_id !== me?.user_id && (
                            confirmDelete === u.user_id ? (
                              <Button variant="danger" className="!px-2 !py-1 text-[12px]"
                                      onClick={() => remove(u.user_id)}>
                                Confirm delete
                              </Button>
                            ) : (
                              <button onClick={() => setConfirmDelete(u.user_id)} title="Delete account"
                                      className="rounded p-1.5 text-ink-muted hover:bg-danger/10 hover:text-danger">
                                <Trash2 className="size-4" />
                              </button>
                            )
                          )}
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
