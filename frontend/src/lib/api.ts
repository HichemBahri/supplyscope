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
  register: (body: {
    email: string; password: string; first_name: string; last_name: string;
    job_title: string; department: string;
  }) => request("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  me: () => request<import("./types").User>("/api/me"),
  updateMe: (body: Partial<Pick<import("./types").User,
    "first_name" | "last_name" | "job_title" | "department">>) =>
    request<import("./types").User>("/api/me", { method: "PATCH", body: JSON.stringify(body) }),
  uploadAvatar: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/me/avatar", {
      method: "PUT",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, (await res.json()).detail ?? "Upload failed");
  },
  adminUsers: () => request<import("./types").User[]>("/api/admin/users"),
  adminUpdateUser: (id: number, body: object) =>
    request<import("./types").User>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  adminDeleteUser: (id: number) =>
    request<void>(`/api/admin/users/${id}`, { method: "DELETE" }),
  dashboards: () => request<import("./types").DashboardSummary[]>("/api/dashboards"),
  createDashboard: (title: string, description?: string) =>
    request<import("./types").DashboardSummary>("/api/dashboards", {
      method: "POST", body: JSON.stringify({ title, description }) }),
  dashboard: (id: number) =>
    request<import("./types").DashboardDetail>(`/api/dashboards/${id}`),
  updateDashboard: (id: number, body: object) =>
    request<import("./types").DashboardSummary>(`/api/dashboards/${id}`, {
      method: "PATCH", body: JSON.stringify(body) }),
  deleteDashboard: (id: number) =>
    request<void>(`/api/dashboards/${id}`, { method: "DELETE" }),
  addChartToDashboard: (id: number, chartId: number) =>
    request<void>(`/api/dashboards/${id}/charts/${chartId}`, { method: "POST" }),
  removeChartFromDashboard: (id: number, chartId: number) =>
    request<void>(`/api/dashboards/${id}/charts/${chartId}`, { method: "DELETE" }),
  comments: (id: number) =>
    request<import("./types").Comment[]>(`/api/dashboards/${id}/comments`),
  postComment: (id: number, content: string) =>
    request<import("./types").Comment>(`/api/dashboards/${id}/comments`, {
      method: "POST", body: JSON.stringify({ content }) }),
  deleteComment: (commentId: number) =>
    request<void>(`/api/dashboards/comments/${commentId}`, { method: "DELETE" }),
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
