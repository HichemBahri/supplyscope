import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";

export default function Register() {
  const [displayName, setDisplayName] = useState("");
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
      await api.register(email, password, displayName);
      const { access_token } = await api.login(email, password);
      login(access_token);
      nav("/chat");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setError("Cet e-mail est déjà enregistré.");
      else if (err instanceof ApiError && err.status === 422) setError("Mot de passe : 8 caractères minimum.");
      else setError("Création impossible — vérifiez que le serveur est lancé.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-navy-900 px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-white/10 bg-card p-6">
        <h1 className="font-display text-lg font-bold text-navy-900">Créer un compte</h1>
        <label className="eyebrow mt-4 block">Nom affiché</label>
        <Input className="mt-1.5" value={displayName} required
               onChange={(e) => setDisplayName(e.target.value)} />
        <label className="eyebrow mt-3 block">E-mail</label>
        <Input className="mt-1.5" type="email" value={email} required
               onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        <label className="eyebrow mt-3 block">Mot de passe</label>
        <Input className="mt-1.5" type="password" value={password} required minLength={8}
               onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <Button className="mt-5 w-full justify-center" disabled={busy}>
          {busy ? "Création…" : "Créer le compte"}
        </Button>
        <p className="mt-4 text-center text-sm text-ink-muted">
          Déjà inscrit ? <Link to="/login" className="font-medium text-action">Se connecter</Link>
        </p>
      </form>
    </div>
  );
}
