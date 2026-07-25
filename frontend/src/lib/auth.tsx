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

  const login = async (t: string) => { setToken(t); setTok(t); await refreshUser(); };
  const logout = () => { setToken(null); setTok(null); setUser(null); };

  return (
    <Ctx.Provider value={{ token, user, login, logout, refreshUser }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
