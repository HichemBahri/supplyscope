import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Factory } from "lucide-react";

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
      login(access_token);
      nav("/chat");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401
        ? "Identifiants incorrects."
        : "Connexion impossible — vérifiez que le serveur est lancé.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-navy-900 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3 text-white">
          <div className="grid size-11 place-items-center rounded-md bg-white/10">
            <Factory className="size-6" />
          </div>
          <div>
            <div className="font-display text-2xl font-bold">SupplyScope</div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-white/50">
              Analytique agentique · GETS
            </div>
          </div>
        </div>
        <form onSubmit={submit} className="rounded-lg border border-white/10 bg-card p-6">
          <h1 className="font-display text-lg font-bold text-navy-900">Se connecter</h1>
          <label className="eyebrow mt-4 block">E-mail</label>
          <Input className="mt-1.5" type="email" value={email} required
                 onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          <label className="eyebrow mt-3 block">Mot de passe</label>
          <Input className="mt-1.5" type="password" value={password} required
                 onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          {error && <p className="mt-3 text-sm text-danger">{error}</p>}
          <Button className="mt-5 w-full justify-center" disabled={busy}>
            {busy ? "Connexion…" : "Se connecter"}
          </Button>
          <p className="mt-4 text-center text-sm text-ink-muted">
            Pas de compte ? <Link to="/register" className="font-medium text-action">Créer un compte</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
