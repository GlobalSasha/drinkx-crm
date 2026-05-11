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
  position: number;
  stages: Stage[];
  // `is_default` removed in Sprint 2.4 G1 (backend dropped the
  // column via migration 0017). Compare pipeline.id to
  // me.workspace.default_pipeline_id to render the «по умолчанию»
  // badge.
}

// ---- Pipeline write shapes (Sprint 2.3 G3) ----
//
// Mirrors apps/api/app/pipelines/schemas.py — StageIn / PipelineCreateIn /
// PipelineUpdateIn. The PipelineEditor's «Цель (дней)» row label binds
// to `rot_days` (the existing rotting threshold) rather than a new
// `target_dwell_days` column — adding a separate column is a 2.4+
// schema change and the rot_days semantics already match what the
// editor surfaces.

export interface StageIn {
  name: string;
  position: number;
  color?: string;
  rot_days?: number;
  probability?: number;
  is_won?: boolean;
  is_lost?: boolean;
  gate_criteria_json?: string[];
}

export interface PipelineCreateIn {
  name: string;
  type?: string;
  stages: StageIn[];
}

export interface PipelineUpdateIn {
  name?: string;
  type?: string;
  stages?: StageIn[];
}

// Structured 409 detail emitted by DELETE /api/pipelines/{id} when the
// pipeline can't be safely removed. The router carries either
// `pipeline_has_leads` (with a lead_count) or `pipeline_is_default`.
export type PipelineDeleteConflict =
  | { code: "pipeline_has_leads"; lead_count: number; message: string }
  | { code: "pipeline_is_default"; message: string };

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
  // Sprint 3.3: optional company link. Backend copies
  // `companies.name` → `leads.company_name` when set, so the snapshot
  // stays in sync from the start.
  company_id?: string | null;
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

export interface FollowupsPendingOut {
  pending_count: number;
  overdue_count: number;
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
  // Sprint 2.3 G2: workspace's canonical default pipeline. Null while
  // the bootstrap path hasn't run yet (impossible in practice — auth
  // bootstrap creates one on first sign-in).
  default_pipeline_id: string | null;
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
  // Sprint 2.4 G5: server-joined from users table. Both NULL when
  // user_id is NULL (system event) or the user has been deleted —
  // the audit table falls back to first-8-chars of user_id.
  user_full_name: string | null;
  user_email: string | null;
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
  // Distinguishes the regular /import flow from the AI bulk-update
  // flow. Only `bulk_update` is set explicitly; the regular flow
  // omits `type`, which the wizard treats as "regular".
  type?: "bulk_update";

  // ---- regular (column-mapper) shape ----
  headers?: string[];
  suggested_mapping?: Record<string, string | null>;
  rows?: Record<string, string>[];        // first 100 preview rows
  all_rows?: Record<string, string>[];    // full payload (kept for /apply)
  validation_errors?: Record<string, string[]>;
  field_catalog?: ImportFieldDef[];
  confirmed_mapping?: Record<string, string | null>;
  mapped_rows?: Record<string, string>[];
  dry_run_stats?: DryRunStats;

  // ---- bulk_update shape ----
  items?: BulkUpdateDiffItem[];
  stats?: {
    to_update: number;
    to_create: number;
    errors: number;
  };
}

export interface BulkUpdateChange {
  field: string;       // 'ai_data.growth_signals' | 'tags' | 'stage' | ...
  op: "add" | "remove" | "replace" | "set";
  value: unknown;
  current_value: unknown | null;
}

export interface BulkUpdateDiffItem {
  action: "update" | "create";
  company_name: string;
  inn: string | null;
  lead_id: string | null;
  changes: BulkUpdateChange[];
  match_confidence:
    | "exact_inn"
    | "exact_name"
    | "exact_id"
    | "not_found"
    | "ambiguous"
    | string;
  error: string | null;
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

// ---- Export ----

export type ExportJobStatus = "pending" | "running" | "done" | "failed";

export type ExportJobFormat = "xlsx" | "csv" | "json" | "yaml" | "md_zip";

export interface ExportJobOut {
  id: string;
  workspace_id: string;
  user_id: string | null;
  status: ExportJobStatus | string;
  format: ExportJobFormat | string;
  row_count: number | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  download_url: string | null;
}

export interface ExportRequestIn {
  format: ExportJobFormat;
  filters?: Record<string, unknown>;
  include_ai_brief?: boolean;
}

// ---- WebForms (Sprint 2.2) ----

export type FieldType = "text" | "email" | "phone" | "textarea" | "select";

export interface FieldDefinition {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  options?: string[] | null;
}

export interface WebFormOut {
  id: string;
  workspace_id: string;
  created_by: string | null;
  name: string;
  slug: string;
  fields_json: FieldDefinition[];
  target_pipeline_id: string | null;
  target_stage_id: string | null;
  redirect_url: string | null;
  is_active: boolean;
  submissions_count: number;
  created_at: string;
  updated_at: string;
  embed_snippet: string | null;
}

export interface WebFormCreateIn {
  name: string;
  fields_json: FieldDefinition[];
  target_pipeline_id?: string | null;
  target_stage_id?: string | null;
  redirect_url?: string | null;
}

export interface WebFormUpdateIn {
  name?: string;
  fields_json?: FieldDefinition[];
  target_pipeline_id?: string | null;
  target_stage_id?: string | null;
  redirect_url?: string | null;
  is_active?: boolean;
}

export interface WebFormPageOut {
  items: WebFormOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface FormSubmissionOut {
  id: string;
  web_form_id: string;
  lead_id: string | null;
  utm_json: Record<string, string> | null;
  source_domain: string | null;
  created_at: string;
}

// ---- Users domain (Sprint 2.4 G1 — Settings «Команда») ----

export interface UserListItemOut {
  id: string;
  email: string;
  name: string;
  role: UserRole | string;
  last_login_at: string | null;
}

export interface UserListOut {
  items: UserListItemOut[];
  total: number;
}

export interface UserInviteIn {
  email: string;
  role: UserRole;
}

export interface UserInviteOut {
  id: string;
  email: string;
  suggested_role: UserRole | string;
  invited_by_user_id: string | null;
  created_at: string;
  accepted_at: string | null;
}

export interface UserRoleUpdateIn {
  role: UserRole;
}

// Structured 409 detail emitted by PATCH /api/users/{id}/role when
// demoting the workspace's last admin would leave it without one.
export interface UserRoleConflict {
  code: "last_admin";
  message: string;
}

// Structured 502 detail emitted by POST /api/users/invite when the
// Supabase admin API call fails — UI shows a «retry later» state.
export interface UserInviteUpstreamError {
  code: "invite_send_failed";
  message: string;
  upstream: string;
}

// ---- Settings → Каналы (Sprint 2.4 G2) ----

export interface GmailChannelOut {
  /** Server has GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET in env. */
  configured: boolean;
  /** Current user has an active ChannelConnection row. */
  connected: boolean;
  last_sync_at: string | null;
}

export interface SmtpConfigOut {
  /** SMTP_HOST is non-empty — server is in stub mode otherwise. */
  configured: boolean;
  host: string;
  port: number;
  from_address: string;
  user: string;
}

export interface ChannelsStatusOut {
  gmail: GmailChannelOut;
  smtp: SmtpConfigOut;
}

// ---- Settings → AI (Sprint 2.4 G3) ----

export interface AISettingsOut {
  daily_budget_usd: number;
  primary_model: string;
  current_spend_usd_today: number;
  available_models: string[];
}

export interface AISettingsUpdateIn {
  daily_budget_usd?: number;
  primary_model?: string;
}

// ---- Custom Attributes (Sprint 2.4 G3) ----

export type AttributeKind = "text" | "number" | "date" | "select";

export interface AttributeOption {
  value: string;
  label: string;
}

export interface CustomAttributeDefinitionOut {
  id: string;
  key: string;
  label: string;
  kind: AttributeKind;
  options_json: AttributeOption[] | null;
  is_required: boolean;
  position: number;
}

export interface CustomAttributeDefinitionCreateIn {
  key: string;
  label: string;
  kind: AttributeKind;
  options_json?: AttributeOption[] | null;
  is_required?: boolean;
}

export interface CustomAttributeDefinitionUpdateIn {
  label?: string;
  options_json?: AttributeOption[] | null;
  is_required?: boolean;
  position?: number;
}

// ---- Sprint 2.6 G4: lead custom fields + reorder ----

export interface LeadAttributeOut {
  definition_id: string;
  key: string;
  label: string;
  kind: AttributeKind;
  options_json: AttributeOption[] | null;
  is_required: boolean;
  position: number;
  // string for text/select; number for number kind; ISO date string for date.
  // null when the manager hasn't set a value yet.
  value: string | number | null;
}

export interface LeadAttributeUpsertIn {
  definition_id: string;
  // Always sent as a string from the input element; backend parses
  // per the definition's kind. Null / empty string clears the value.
  value: string | null;
}

export interface CustomAttributeReorderIn {
  ordered_ids: string[];
}

// ---- Message Templates (Sprint 2.4 G4) ----

export type TemplateChannel = "email" | "tg" | "sms";

export interface MessageTemplateOut {
  id: string;
  name: string;
  channel: TemplateChannel;
  category: string | null;
  text: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageTemplateCreate {
  name: string;
  channel: TemplateChannel;
  category?: string | null;
  text: string;
}

export interface MessageTemplateUpdate {
  name?: string;
  channel?: TemplateChannel;
  category?: string | null;
  text?: string;
}

// ---- Automation Builder (Sprint 2.5 G1) ----

export type AutomationTrigger =
  | "stage_change"
  | "form_submission"
  | "inbox_match";

export type AutomationAction =
  | "send_template"
  | "create_task"
  | "move_stage";

export type AutomationRunStatus =
  | "queued"
  | "success"
  | "skipped"
  | "failed";

// Sprint 2.7 G2 — multi-step automation chains.
export type AutomationStepType =
  | "delay_hours"
  | "send_template"
  | "create_task"
  | "move_stage";

export type AutomationStepRunStatus =
  | "pending"
  | "success"
  | "skipped"
  | "failed";

export interface AutomationStep {
  type: AutomationStepType;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config: Record<string, any>;
}

export interface AutomationOut {
  id: string;
  name: string;
  trigger: AutomationTrigger;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  trigger_config_json: Record<string, any> | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  condition_json: Record<string, any> | null;
  action_type: AutomationAction;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  action_config_json: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  steps_json: Array<Record<string, any>> | null;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationCreate {
  name: string;
  trigger: AutomationTrigger;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  trigger_config_json?: Record<string, any> | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  condition_json?: Record<string, any> | null;
  action_type: AutomationAction;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  action_config_json: Record<string, any>;
  steps_json?: AutomationStep[] | null;
  is_active?: boolean;
}

export interface AutomationUpdate {
  name?: string;
  trigger?: AutomationTrigger;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  trigger_config_json?: Record<string, any> | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  condition_json?: Record<string, any> | null;
  action_type?: AutomationAction;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  action_config_json?: Record<string, any>;
  steps_json?: AutomationStep[] | null;
  is_active?: boolean;
}

export interface AutomationRunOut {
  id: string;
  automation_id: string;
  lead_id: string | null;
  status: AutomationRunStatus;
  error: string | null;
  executed_at: string;
}

export interface AutomationStepRunOut {
  id: string;
  automation_run_id: string;
  step_index: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  step_json: Record<string, any>;
  scheduled_at: string;
  executed_at: string | null;
  status: AutomationStepRunStatus;
  error: string | null;
}

// Sprint 3.1 — Lead AI Agent. Backend contract lives in
// `apps/api/app/lead_agent/schemas.py`. Pure-JSON shapes; no
// timestamps because the runner is stateless across calls (the
// suggestion is overwritten in `lead.agent_state['suggestion']`
// rather than appended).
export interface AgentSuggestion {
  text: string;
  action_label: string | null;
  confidence: number;
}

export interface AgentSuggestionResponse {
  suggestion: AgentSuggestion | null;
}

export interface AgentChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AgentChatRequest {
  message: string;
  history: AgentChatMessage[];
}

export interface AgentChatResponse {
  reply: string;
  updated_history: AgentChatMessage[];
}

// ---------------------------------------------------------------------------
// Sprint 3.3 — Companies + Global Search
// ---------------------------------------------------------------------------

export interface CompanyOut {
  id: string;
  workspace_id: string;
  name: string;
  normalized_name: string;
  legal_name: string | null;
  inn: string | null;
  kpp: string | null;
  domain: string | null;
  website: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  address: string | null;
  primary_segment: string | null;
  employee_range: string | null;
  notes: string | null;
  is_archived: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyLeadSummary {
  id: string;
  company_name: string;
  stage_id: string | null;
  score: number;
  fit_score: number | null;
  assigned_to: string | null;
  created_at: string;
}

export interface CompanyContactSummary {
  id: string;
  name: string;
  title: string | null;
  email: string | null;
  phone: string | null;
  lead_id: string;
}

export interface CompanyActivitySummary {
  id: string;
  lead_id: string;
  type: string;
  subject: string | null;
  body: string | null;
  created_at: string;
}

export interface CompanyCardOut extends CompanyOut {
  leads: CompanyLeadSummary[];
  contacts: CompanyContactSummary[];
  recent_activities: CompanyActivitySummary[];
}

export interface CompanyCreate {
  name: string;
  legal_name?: string | null;
  inn?: string | null;
  kpp?: string | null;
  website?: string | null;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  address?: string | null;
  primary_segment?: string | null;
  employee_range?: string | null;
  notes?: string | null;
}

export interface CompanyUpdate extends Partial<CompanyCreate> {}

export interface CompanyDuplicateCandidate {
  id: string;
  name: string;
  inn: string | null;
  leads_count: number;
}

export interface DuplicateWarningResponse {
  error: "duplicate_warning";
  candidates: CompanyDuplicateCandidate[];
}

export interface CompanyListOut {
  items: CompanyOut[];
  total: number;
}

export type SearchHitType = "company" | "lead" | "contact";

export interface SearchHit {
  type: SearchHitType;
  id: string;
  title: string;
  subtitle: string | null;
  lead_id: string | null;
  url: string;
  rank: number | null;
}

export interface SearchResponse {
  items: SearchHit[];
  total: number;
  query: string;
  mode: "ilike" | "trgm" | "empty";
}
