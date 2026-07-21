import { createContext, useContext, useState, type ReactNode } from "react";
import { getToken, setToken } from "./api";

interface AuthCtx {
  token: string | null;
  login: (token: string) => void;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>({ token: null, login: () => {}, logout: () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(getToken());
  const login = (t: string) => { setToken(t); setTok(t); };
  const logout = () => { setToken(null); setTok(null); };
  return <Ctx.Provider value={{ token, login, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
