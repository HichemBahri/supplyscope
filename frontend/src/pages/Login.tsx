import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import logo from "../assets/gets-logo.png";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const nav = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const { access_token } = await api.login(email, password);
      await login(access_token);
      nav("/chat");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError("Email not verified — finish sign-up with the code we emailed you (Register page).");
        setBusy(false); return;
      }
      if (err instanceof ApiError && err.status === 423) {
        setError("Account temporarily locked after repeated failures — try again in 15 minutes.");
        setBusy(false); return;
      }
      setError(err instanceof ApiError && err.status === 401
        ? "Incorrect email or password."
        : "Can't reach the server — make sure the backend is running.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-navy-900 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3 text-white">
          <img src={logo} alt="GETS" className="size-12 rounded-full bg-white p-0.5" />
          <div>
            <div className="font-display text-2xl font-bold">SupplyScope</div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-white/50">
              Agentic Analytics · GETS
            </div>
          </div>
        </div>
        <form onSubmit={submit} className="rounded-lg border border-white/10 bg-card p-6">
          <h1 className="font-display text-lg font-bold text-navy-900">Sign in</h1>
          <label className="eyebrow mt-4 block">Email</label>
          <Input className="mt-1.5" type="email" value={email} required
                 onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          <label className="eyebrow mt-3 block">Password</label>
          <Input className="mt-1.5" type="password" value={password} required
                 onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          {error && <p className="mt-3 text-sm text-danger">{error}</p>}
          <Button className="mt-5 w-full justify-center" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <p className="mt-4 text-center text-sm text-ink-muted">
            No account yet? <Link to="/register" className="font-medium text-action">Create one</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
