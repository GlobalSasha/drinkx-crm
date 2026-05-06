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
