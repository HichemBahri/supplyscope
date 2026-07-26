export interface ChartSpec {
  chart_type: "bar" | "line" | "pie" | "scatter" | "kpi" | "table";
  title: string;
  x_field?: string;
  y_fields?: string[];
  y_field?: string;
  label_field?: string;
  value_field?: string;
  color_field?: string | null;
  orientation?: "v" | "h";
  stacked?: boolean;
  unit?: string | null;
}

export interface ResultMeta {
  columns: string[];
  preview_rows: unknown[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
  attempts: { sql: string; error: string }[];
  failed: boolean;
}

export interface Message {
  message_id: number;
  role: "user" | "assistant";
  content: string;
  sql_query: string | null;
  chart: ChartSpec | null;
  result_meta: ResultMeta | null;
  created_at: string;
}

export interface Conversation {
  conversation_id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface SavedChart {
  chart_id: number;
  title: string;
  sql_query: string;
  chart_spec: ChartSpec;
  created_at: string;
  updated_at: string;
}

export interface ChartData {
  chart_id: number;
  chart_spec: ChartSpec;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
}

export interface ChartUpdateEvent extends ChartData {
  title: string;
  source_tables: string[];
  refreshed_at: string;
}

export interface ChatTurn {
  conversation_id: number;
  user_message: Message;
  assistant_message: Message;
}

export interface User {
  user_id: number;
  email: string;
  first_name: string;
  last_name: string;
  job_title: string;
  department: string;
  role: "admin" | "analyst";
  has_avatar: boolean;
  created_at: string;
}

export const DEPARTMENTS = [
  "Supply Chain", "Tendering", "Engineering", "Finance", "IT", "Management",
] as const;

export interface DashboardSummary {
  dashboard_id: number;
  owner_id: number;
  title: string;
  description: string | null;
  is_shared: boolean;
  owner_first_name: string;
  owner_last_name: string;
  chart_count: number;
  created_at: string;
  updated_at: string;
}

export interface DashboardChart {
  chart_id: number;
  title: string;
  sql_query: string;
  chart_spec: ChartSpec;
  position: number;
}

export interface DashboardDetail extends DashboardSummary {
  charts: DashboardChart[];
  can_edit: boolean;
}

export interface Comment {
  comment_id: number;
  dashboard_id: number;
  user_id: number;
  content: string;
  first_name: string;
  last_name: string;
  job_title: string;
  has_avatar: boolean;
  created_at: string;
}
