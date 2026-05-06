// TypeScript types mirroring backend Pydantic schemas.

export type DealType = "new" | "upsell" | "renewal" | "partner";
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
