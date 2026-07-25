import { useRef, useState, type FormEvent } from "react";
import { Camera } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Avatar } from "../components/Avatar";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Card } from "../components/ui/Card";
import { DEPARTMENTS } from "../lib/types";

export default function Profile() {
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState({
    first_name: user?.first_name ?? "", last_name: user?.last_name ?? "",
    job_title: user?.job_title ?? "", department: user?.department ?? "Supply Chain",
  });
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  if (!user) return null;

  const set = (k: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setMessage(null);
    try {
      await api.updateMe(form);
      await refreshUser();
      setMessage({ kind: "ok", text: "Profile saved." });
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof ApiError ? err.message : "Save failed — try again." });
    } finally {
      setBusy(false);
    }
  };

  const pickAvatar = async (file: File | undefined) => {
    if (!file) return;
    setMessage(null);
    try {
      await api.uploadAvatar(file);
      await refreshUser();
      setMessage({ kind: "ok", text: "Photo updated." });
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof ApiError ? err.message : "Upload failed." });
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-xl">
        <h1 className="font-display text-xl font-bold text-navy-900">My profile</h1>
        <Card className="mt-4 p-6">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="group relative rounded-full focus-visible:outline-2 focus-visible:outline-action"
              title="Change photo"
            >
              <Avatar user={user} size={72} />
              <span className="absolute inset-0 grid place-items-center rounded-full bg-navy-900/0 text-white opacity-0 transition-opacity group-hover:bg-navy-900/45 group-hover:opacity-100">
                <Camera className="size-5" />
              </span>
            </button>
            <div>
              <div className="font-display text-lg font-bold text-navy-900">
                {user.first_name} {user.last_name}
              </div>
              <div className="text-sm text-ink-muted">{user.email}</div>
              <div className="eyebrow mt-1">{user.role === "admin" ? "Administrator" : "Analyst"} · {user.department}</div>
            </div>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp"
                   className="hidden" onChange={(e) => pickAvatar(e.target.files?.[0])} />
          </div>

          <form onSubmit={save} className="mt-6">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="eyebrow block">First name</label>
                <Input className="mt-1.5" value={form.first_name} required onChange={set("first_name")} />
              </div>
              <div>
                <label className="eyebrow block">Last name</label>
                <Input className="mt-1.5" value={form.last_name} required onChange={set("last_name")} />
              </div>
            </div>
            <label className="eyebrow mt-3 block">Job title</label>
            <Input className="mt-1.5" value={form.job_title} required onChange={set("job_title")} />
            <label className="eyebrow mt-3 block">Department</label>
            <select value={form.department} onChange={set("department")}
                    className="mt-1.5 w-full rounded-md border border-line bg-card px-3 py-2 text-sm focus:border-action focus:outline-none focus:ring-2 focus:ring-action/20">
              {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
            </select>
            {message && (
              <p className={`mt-3 text-sm ${message.kind === "ok" ? "text-ok" : "text-danger"}`}>
                {message.text}
              </p>
            )}
            <Button className="mt-5" disabled={busy}>
              {busy ? "Saving…" : "Save changes"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
