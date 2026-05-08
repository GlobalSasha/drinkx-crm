// TypeScript types mirroring backend Pydantic schemas.

export type DealType =
  | "enterprise_direct"
  | "qsr"
  | "distributor_partner"
  | "raw_materials"
  | "private_small"
  | "service_repeat";

export type ContactRoleType =
  | "economic_buyer"
  | "champion"
  | "technical"
  | "operational";

export type ContactConfidence = "low" | "medium" | "high";
export type ContactVerifiedStatus = "to_verify" | "verified" | "invalid";
export type Priority = "A" | "B" | "C" | "D";
export type AssignmentStatus = "pool" | "assigned" | "transferred";

export interface Stage {
  id: string;
  pipeline_id: string;
  name: string;
  position: number;
  color: string;
  rot_days: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  gate_criteria_json: string[];
}

export interface Pipeline {
  id: string;
  workspace_id: string;
  name: string;
  type: string;
  is_default: boolean;
  position: number;
  stages: Stage[];
}

export interface LeadOut {
  id: string;
  workspace_id: string;
  pipeline_id: string | null;
  stage_id: string | null;
  company_name: string;
  segment: string | null;
  city: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  inn: string | null;
  source: string | null;
  tags_json: string[];
  deal_type: DealType | null;
  priority: Priority | null;
  score: number;
  fit_score: number | null;
  blocker: string | null;
  next_step: string | null;
  next_action_at: string | null;
  assignment_status: AssignmentStatus;
  assigned_to: string | null;
  assigned_at: string | null;
  transferred_from: string | null;
  transferred_at: string | null;
  is_rotting_stage: boolean;
  is_rotting_next_step: boolean;
  last_activity_at: string | null;
  archived_at: string | null;
  won_at: string | null;
  lost_at: string | null;
  lost_reason: string | null;
  created_at: string;
  updated_at: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ai_data?: Record<string, any> | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  pilot_contract_json?: Record<string, any> | null;
}

export interface LeadCreate {
  company_name: string;
  segment?: string | null;
  city?: string | null;
  email?: string | null;
  phone?: string | null;
  deal_type?: DealType | null;
  priority?: Priority | null;
  pipeline_id?: string | null;
  stage_id?: string | null;
}

export interface LeadUpdate {
  company_name?: string;
  segment?: string | null;
  city?: string | null;
  email?: string | null;
  phone?: string | null;
  deal_type?: DealType | null;
  priority?: Priority | null;
  score?: number;
  blocker?: string | null;
  next_step?: string | null;
  stage_id?: string | null;
}

export interface LeadListOut {
  items: LeadOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface SprintCreateIn {
  cities: string[];
  segment?: string | null;
  limit?: number | null;
}

export interface SprintCreateOut {
  claimed_count: number;
  requested: number;
  items: LeadOut[];
}

export interface MoveStageIn {
  stage_id: string;
  gate_skipped?: boolean;
  skip_reason?: string | null;
  lost_reason?: string | null;
}

export interface GateViolationOut {
  code: string;
  message: string;
  hard: boolean;
}

export interface MoveStageBlockedDetail {
  message: string;
  violations: GateViolationOut[];
}

// LeadUpdate extended with pilot and next_action_at
export interface LeadUpdateExtended extends LeadUpdate {
  next_action_at?: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  pilot_contract_json?: Record<string, any> | null;
}

// ---- Contacts ----

export interface ContactOut {
  id: string;
  lead_id: string;
  name: string;
  title: string | null;
  role_type: ContactRoleType | null;
  email: string | null;
  phone: string | null;
  telegram_url: string | null;
  linkedin_url: string | null;
  source: string | null;
  confidence: ContactConfidence;
  verified_status: ContactVerifiedStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactCreate {
  name: string;
  title?: string | null;
  role_type?: ContactRoleType | null;
  email?: string | null;
  phone?: string | null;
  telegram_url?: string | null;
  linkedin_url?: string | null;
  source?: string | null;
  confidence?: ContactConfidence;
  verified_status?: ContactVerifiedStatus;
  notes?: string | null;
}

export interface ContactUpdate {
  name?: string;
  title?: string | null;
  role_type?: ContactRoleType | null;
  email?: string | null;
  phone?: string | null;
  telegram_url?: string | null;
  linkedin_url?: string | null;
  source?: string | null;
  confidence?: ContactConfidence | null;
  verified_status?: ContactVerifiedStatus | null;
  notes?: string | null;
}

// ---- Activities ----

export interface ActivityOut {
  id: string;
  lead_id: string;
  user_id: string | null;
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload_json: Record<string, any>;
  task_due_at: string | null;
  reminder_trigger_at: string | null;
  file_url: string | null;
  file_kind: string | null;
  channel: string | null;
  direction: string | null;
  subject: string | null;
  body: string | null;
  // Email-specific (Sprint 2.0)
  from_identifier: string | null;
  to_identifier: string | null;
  gmail_message_id: string | null;
  task_done: boolean;
  task_completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityCreate {
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload_json?: Record<string, any>;
  task_due_at?: string | null;
  reminder_trigger_at?: string | null;
  file_url?: string | null;
  file_kind?: string | null;
  channel?: string | null;
  direction?: string | null;
  subject?: string | null;
  body?: string | null;
}

export interface ActivityListOut {
  items: ActivityOut[];
  next_cursor: string | null;
}

// ---- Followups ----

export interface FollowupOut {
  id: string;
  lead_id: string;
  name: string;
  due_at: string | null;
  status: string;
  reminder_kind: string;
  notes: string | null;
  position: number;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FollowupCreate {
  name: string;
  due_at?: string | null;
  status?: string;
  reminder_kind?: string;
  notes?: string | null;
  position?: number;
}

export interface FollowupUpdate {
  name?: string;
  due_at?: string | null;
  status?: string | null;
  reminder_kind?: string | null;
  notes?: string | null;
  position?: number | null;
}

// ---- Scoring ----

export interface ScoringCriterion {
  key: string;
  label: string;
  weight: number;
  max_value: number;
}

export const DEFAULT_SCORING_CRITERIA: ScoringCriterion[] = [
  { key: "scale_potential",       label: "Масштаб потенциала",       weight: 20, max_value: 5 },
  { key: "pilot_probability_90d", label: "Вероятность пилота 90д",   weight: 15, max_value: 5 },
  { key: "economic_buyer",        label: "Экономический покупатель", weight: 15, max_value: 5 },
  { key: "reference_value",       label: "Референсная ценность",     weight: 15, max_value: 5 },
  { key: "standard_product",      label: "Стандартный продукт",      weight: 10, max_value: 5 },
  { key: "data_readiness",        label: "Готовность данных",        weight: 10, max_value: 5 },
  { key: "partner_potential",     label: "Партнёрский потенциал",    weight: 10, max_value: 5 },
  { key: "budget_confirmed",      label: "Бюджет подтверждён",       weight: 5,  max_value: 5 },
];

export const DEFAULT_GATE_CRITERIA: Record<number, string[]> = {
  1: ["ICP соответствие подтверждено", "ЛПР идентифицирован", "Сегмент и тип сделки определены", "Приоритет A/B/C/D присвоен"],
  2: ["Проведён discovery-звонок (≥30 мин)", "Боль/потребность зафиксирована", "Бюджет предварительно обсуждён"],
  3: ["Solution fit подтверждён", "Pilot feasibility оценена", "Технический покупатель вовлечён"],
  4: ["КП отправлено", "ROI-расчёт согласован", "Следующий шаг назначен с датой"],
  5: ["Экономический покупатель идентифицирован", "Все стейкхолдеры вовлечены", "Внутренний чемпион активен"],
  6: ["Договор отправлен", "Юридическое согласование начато", "Пилот-план согласован"],
  7: ["Договор подписан", "Производство запущено", "Pilot Success Contract заполнен"],
  8: ["Оборудование доставлено", "Установка подтверждена", "Пилотные цели зафиксированы"],
  9: ["Пилот завершён", "KPI зафиксированы", "Решение о масштабировании принято"],
  10: [],
};

export function tierFromScore(score: number): "A" | "B" | "C" | "D" {
  if (score >= 80) return "A";
  if (score >= 60) return "B";
  if (score >= 40) return "C";
  return "D";
}

// ---- Enrichment ----

export type EnrichmentStatus = "running" | "succeeded" | "failed" | "skipped";

export interface DecisionMakerHint {
  name: string;
  title: string;
  role: string; // canonical: economic_buyer/champion/technical_buyer/operational_buyer/"" — but backend accepts any
  confidence: string; // canonical: high/medium/low — backend permissive
  source: string;
}

export interface ResearchOutput {
  company_profile: string;
  network_scale: string;
  geography: string;
  // Backend may return either a string or a list of strings — frontend
  // normalizes via asList/asText helpers in AIBriefTab.
  formats: string | string[];
  coffee_signals: string | string[];
  growth_signals: string[];
  risk_signals: string[];
  decision_maker_hints: DecisionMakerHint[];
  fit_score: number;
  next_steps: string[];
  // Loosened from Literal — backend accepts any string now (LLMs return
  // Russian words sometimes); UI maps known values, leaves rest as-is.
  urgency: string;
  sources_used: string[];
  notes: string;
  score_rationale?: string;
}

export interface EnrichmentRun {
  id: string;
  lead_id: string;
  user_id: string | null;
  status: EnrichmentStatus;
  provider: string | null;
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number; // Decimal serialized as string by pydantic; coerce on read
  duration_ms: number;
  sources_used: string[];
  error: string | null;
  result_json: ResearchOutput | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EnrichmentTriggerResponse {
  enrichment_run_id: string;
  status: EnrichmentStatus;
}

// ---- Daily Plan ----

export type TimeBlock = "morning" | "midday" | "afternoon" | "evening";
export type TaskKind = "call" | "email" | "meeting" | "research" | "follow_up";
export type DailyPlanStatus = "pending" | "generating" | "ready" | "failed";

export interface DailyPlanItem {
  id: string;
  daily_plan_id: string;
  lead_id: string | null;
  position: number;
  priority_score: number;
  estimated_minutes: number;
  time_block: TimeBlock | null;
  task_kind: TaskKind;
  hint_one_liner: string;
  done: boolean;
  done_at: string | null;
  // joined
  lead_company_name: string | null;
  lead_segment: string | null;
  lead_city: string | null;
}

export interface DailyPlanSummary {
  total_minutes?: number;
  count?: number;
  urgency_breakdown?: { high?: number; medium?: number; low?: number };
}

export interface DailyPlan {
  id: string;
  workspace_id: string;
  user_id: string;
  plan_date: string;        // YYYY-MM-DD
  generated_at: string | null;
  status: DailyPlanStatus;
  generation_error: string | null;
  summary_json: DailyPlanSummary;
  items: DailyPlanItem[];
  created_at: string;
  updated_at: string;
}

export interface RegenerateResponse {
  plan_id: string | null;
  status: DailyPlanStatus;
  task_id: string | null;
}

// ---- Notifications (Sprint 1.5) ----

export type NotificationKind =
  | "lead_transferred"
  | "enrichment_done"
  | "enrichment_failed"
  | "daily_plan_ready"
  | "followup_due"
  | "mention"
  | "system";

export interface NotificationOut {
  id: string;
  kind: NotificationKind | string; // backend permissive
  title: string;
  body: string;
  lead_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListOut {
  items: NotificationOut[];
  total: number;
  unread: number;
  page: number;
  page_size: number;
}

export interface MarkAllReadOut {
  affected: number;
}

// ---- Auth: /auth/me ----

export interface WorkspaceOut {
  id: string;
  name: string;
  plan: string;
  sprint_capacity_per_week: number;
}

export type UserRole = "admin" | "head" | "manager";

export interface MeOut {
  id: string;
  email: string;
  name: string;
  role: UserRole | string; // backend stores any 20-char string; coerce on read
  timezone: string;
  max_active_deals: number;
  specialization: string[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  working_hours_json: Record<string, any>;
  onboarding_completed: boolean;
  last_login_at: string | null;
  workspace: WorkspaceOut;
}

// ---- Audit (Sprint 1.5 group 4) ----

export type AuditAction =
  | "lead.create"
  | "lead.transfer"
  | "lead.move_stage"
  | "enrichment.trigger"
  | "daily_plan.regenerate";

export interface AuditLogOut {
  id: string;
  workspace_id: string;
  user_id: string | null;
  action: AuditAction | string;
  entity_type: string;
  entity_id: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delta_json: Record<string, any> | null;
  created_at: string;
}

export interface AuditLogPageOut {
  items: AuditLogOut[];
  total: number;
  page: number;
  page_size: number;
}

// ---- Inbox (Sprint 2.0) ----

export type InboxItemStatus = "pending" | "matched" | "dismissed" | "created_lead";
export type EmailDirection = "inbound" | "outbound";
export type InboxAction = "match_lead" | "create_lead" | "add_contact";

export interface SuggestedAction {
  action: InboxAction | "ignore" | string;
  company_name: string;
  contact_name: string;
  confidence: number;          // 0..1
  lead_id: string | null;
}

export interface InboxItemOut {
  id: string;
  workspace_id: string;
  user_id: string | null;
  gmail_message_id: string;
  from_email: string;
  to_emails: string[];
  subject: string | null;
  body_preview: string | null;
  received_at: string;
  direction: EmailDirection | string;
  status: InboxItemStatus | string;
  suggested_action: SuggestedAction | null;
  created_at: string;
}

export interface InboxPageOut {
  items: InboxItemOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface InboxConfirmIn {
  action: InboxAction;
  lead_id?: string | null;
  company_name?: string | null;
  contact_name?: string | null;
}

export interface InboxCountOut {
  pending: number;
}

// ---- Import / export (Sprint 2.1) ----

export type ImportJobStatus =
  | "uploaded"
  | "mapping"
  | "previewed"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type ImportJobFormat =
  | "xlsx"
  | "csv"
  | "yaml"
  | "json"
  | "bitrix24"
  | "amocrm"
  | "bulk_update_yaml";

export interface ImportFieldDef {
  key: string;
  label_ru: string;
  required: boolean;
}

export interface DryRunStats {
  will_create: number;
  will_skip: number;
  errors: Record<string, string[]>; // row_index → list of messages
}

export interface ImportDiffPayload {
  headers: string[];
  suggested_mapping: Record<string, string | null>;
  rows: Record<string, string>[];        // first 100 preview rows
  all_rows: Record<string, string>[];    // full payload (kept for /apply)
  validation_errors: Record<string, string[]>;
  field_catalog: ImportFieldDef[];

  // Populated after confirm-mapping
  confirmed_mapping?: Record<string, string | null>;
  mapped_rows?: Record<string, string>[];
  dry_run_stats?: DryRunStats;
}

export interface ImportJobOut {
  id: string;
  workspace_id: string;
  user_id: string | null;
  status: ImportJobStatus | string;
  format: ImportJobFormat | string;
  source_filename: string;
  upload_size_bytes: number;
  total_rows: number;
  processed: number;
  succeeded: number;
  failed: number;
  error_summary: string | null;
  diff_json: ImportDiffPayload | null;
  created_at: string;
  finished_at: string | null;
}
