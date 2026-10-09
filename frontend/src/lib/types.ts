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
  role: "admin" | "analyst" | "manager";
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

export interface MlModel {
  model_id: number;
  model_name: string;
  task: "classification" | "regression";
  algo: string;
  version: number;
  trained_at: string;
  split_date: string | null;
  train_rows: number;
  test_rows: number;
  metrics: Record<string, number | number[][]>;
  comparison: Record<string, Record<string, number | number[][]>> |
              Record<string, Record<string, Record<string, number>>>;
  feature_importance: { feature: string; importance: number }[];
  is_active: boolean;
}

export interface RiskPrediction {
  prediction_id: number;
  shipment_ref: string;
  po_number: string;
  project_code: string | null;
  supplier_name: string;
  promised_delivery_date: string | null;
  status: string | null;
  probability: number;
  risk_band: "high" | "medium" | "low";
  model_version: number;
  scored_at: string;
}

export interface ForecastPoint {
  category: string;
  month: string;
  price_index: number;
  kind: "history" | "forecast";
}

export interface Alert {
  alert_id: number;
  rule_code: string;
  entity_ref: string;
  severity: "info" | "warning" | "critical";
  title: string;
  detail: string;
  context: Record<string, unknown>;
  status: "active" | "acknowledged" | "resolved";
  first_seen: string;
  last_seen: string;
  acknowledged_by: number | null;
  acknowledged_at: string | null;
}

export interface AlertSummary {
  critical: number; warning: number; info: number; total: number;
}

export interface AlertRule {
  code: string; name: string; severity: string; description: string;
}

export interface RecoBreakdownItem {
  criterion: string; weight: number; raw: number | null;
  normalized: number; contribution: number; direction: string;
}
export interface RecoCandidate {
  supplier_id: number; supplier_code: string; name: string; country: string;
  score: number; cold_start: boolean;
  evidence: { category_quotes: number; delivered_shipments: number; qc_receipts: number };
  breakdown: RecoBreakdownItem[];
}
export interface RecoResponse {
  category: string; destination_country: string; preset: string;
  weights: Record<string, number>; method: string; ml_risk_included: boolean;
  candidates: RecoCandidate[]; note?: string;
}

export interface OptTotals {
  price_tnd: number; expected_penalty_tnd: number; expected_total_tnd: number;
  avg_p_late: number; avg_lead_days: number;
}
export interface OptAllocation {
  rfq_ref: string; category: string; project: string; destination: string;
  supplier_code: string; supplier_name: string; price_tnd: number;
  p_late: number; expected_cost_tnd: number; was_cheapest_bid: boolean;
  was_actual_award: boolean; bids_considered: number;
}
export interface OptResponse {
  status: string; solver_ms: number; method: string;
  parameters: Record<string, number | null>;
  open_rfqs: number; candidate_bids: number;
  allocations: OptAllocation[];
  totals: OptTotals; actual_allocation: OptTotals; baseline_cheapest: OptTotals;
  savings_vs_actual_tnd: number; savings_vs_actual_pct: number;
  savings_vs_cheapest_tnd: number;
  constraints_report: { budget_binding: boolean; max_supplier_share_actual: number;
    concentration_ceiling: number; concentration_mode: string; risk_ceiling: number;
    bids_excluded_by_risk: number; diverged_from_cheapest: number;
    bids_above_ceiling: number; rfqs_ceiling_enforced: number;
    rfqs_ceiling_waived: number; waived_rfq_refs: string[] };
  note?: string;
}

export interface AuditEntry {
  audit_id: number;
  user_id: number | null;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
  email?: string | null;
  first_name?: string | null;
  last_name?: string | null;
}
