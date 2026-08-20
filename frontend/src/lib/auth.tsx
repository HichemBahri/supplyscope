import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { User } from "./types";

interface AuthCtx {
  token: string | null;
  user: User | null;
  login: (token: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>({
  token: null, user: null,
  login: async () => {}, logout: () => {}, refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(getToken());
  const [user, setUser] = useState<User | null>(null);

  const refreshUser = async () => {
    try { setUser(await api.me()); }
    catch { setToken(null); setTok(null); setUser(null); }
  };

  useEffect(() => { if (token) refreshUser(); }, []);  // hydrate on reload

  // Re-verify identity when the tab regains focus: a role change or
  // deactivation applied elsewhere (e.g. an admin promoting this user)
  // then takes effect without a manual reload. Roles live only in the DB
  // (never in the token), so /api/me is always the current truth.
  useEffect(() => {
    const revalidate = () => {
      if (getToken() && document.visibilityState === "visible") refreshUser();
    };
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => {
      window.removeEventListener("focus", revalidate);
      document.removeEventListener("visibilitychange", revalidate);
    };
  }, []);

  const login = async (t: string) => { setToken(t); setTok(t); await refreshUser(); };
  const logout = () => { setToken(null); setTok(null); setUser(null); };

  return (
    <Ctx.Provider value={{ token, user, login, logout, refreshUser }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
