import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { DEPARTMENTS } from "../lib/types";
import logo from "../assets/gets-logo.png";

export default function Register() {
  const [form, setForm] = useState({
    first_name: "", last_name: "", email: "", password: "",
    job_title: "", department: "Supply Chain",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const nav = useNavigate();

  const set = (k: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await api.register(form);
      const { access_token } = await api.login(form.email, form.password);
      await login(access_token);
      nav("/chat");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setError("This email is already registered.");
      else if (err instanceof ApiError && err.status === 422) setError("Check the form: password needs at least 8 characters.");
      else setError("Can't reach the server — make sure the backend is running.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-navy-900 px-4 py-8">
      <form onSubmit={submit} className="w-full max-w-md rounded-lg border border-white/10 bg-card p-6">
        <div className="mb-4 flex items-center gap-3">
          <img src={logo} alt="GETS" className="size-10 rounded-full bg-white p-0.5" />
          <h1 className="font-display text-lg font-bold text-navy-900">Create your account</h1>
        </div>
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
        <Input className="mt-1.5" value={form.job_title} required minLength={2}
               placeholder="e.g. Procurement Engineer" onChange={set("job_title")} />
        <label className="eyebrow mt-3 block">Department</label>
        <select
          value={form.department} onChange={set("department")}
          className="mt-1.5 w-full rounded-md border border-line bg-card px-3 py-2 text-sm focus:border-action focus:outline-none focus:ring-2 focus:ring-action/20"
        >
          {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
        </select>
        <label className="eyebrow mt-3 block">Email</label>
        <Input className="mt-1.5" type="email" value={form.email} required
               onChange={set("email")} autoComplete="email" />
        <label className="eyebrow mt-3 block">Password</label>
        <Input className="mt-1.5" type="password" value={form.password} required minLength={8}
               onChange={set("password")} autoComplete="new-password" />
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <Button className="mt-5 w-full justify-center" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </Button>
        <p className="mt-4 text-center text-sm text-ink-muted">
          Already registered? <Link to="/login" className="font-medium text-action">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
