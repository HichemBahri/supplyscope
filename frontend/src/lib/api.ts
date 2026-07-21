/** Typed fetch wrapper for the SupplyScope API. */
const BASE = "";

let authToken: string | null = localStorage.getItem("supplyscope.token");

export function setToken(token: string | null) {
  authToken = token;
  if (token) localStorage.setItem("supplyscope.token", token);
  else localStorage.removeItem("supplyscope.token");
}

export function getToken(): string | null {
  return authToken;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const res = await fetch(BASE + path, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string, display_name: string) =>
    request("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password, display_name }) }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  chat: (question: string, conversation_id?: number, tier: string = "fast") =>
    request<import("./types").ChatTurn>("/api/chat", {
      method: "POST", body: JSON.stringify({ question, conversation_id, tier }),
    }),
  conversations: () => request<import("./types").Conversation[]>("/api/conversations"),
  messages: (id: number) => request<import("./types").Message[]>(`/api/conversations/${id}/messages`),
  saveChart: (title: string, sql_query: string, chart_spec: object) =>
    request<import("./types").SavedChart>("/api/charts", {
      method: "POST", body: JSON.stringify({ title, sql_query, chart_spec }),
    }),
  charts: () => request<import("./types").SavedChart[]>("/api/charts"),
  chartData: (id: number) => request<import("./types").ChartData>(`/api/charts/${id}/data`),
  deleteChart: (id: number) => request<void>(`/api/charts/${id}`, { method: "DELETE" }),
};
