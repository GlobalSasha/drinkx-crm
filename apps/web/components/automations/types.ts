import type {
  AutomationAction,
  AutomationRunStatus,
  AutomationStepRunStatus,
  AutomationStepType,
  AutomationTrigger,
} from "@/lib/types";

export const TRIGGER_LABELS: Record<AutomationTrigger, string> = {
  stage_change: "Смена стадии",
  form_submission: "Заявка с формы",
  inbox_match: "Почта привязана к лиду",
};

export const ACTION_LABELS: Record<AutomationAction, string> = {
  send_template: "Отправить шаблон",
  create_task: "Создать задачу",
  move_stage: "Перевести стадию",
};

export const RUN_STATUS_LABELS: Record<AutomationRunStatus, string> = {
  queued: "В очереди",
  success: "Успешно",
  skipped: "Пропущено",
  failed: "Ошибка",
};

// Sprint 2.7 G2 — multi-step chain step labels.
export const STEP_TYPE_LABELS: Record<AutomationStepType, string> = {
  delay_hours: "Пауза",
  send_template: "Отправить шаблон",
  create_task: "Создать задачу",
  move_stage: "Перевести стадию",
};

export const STEP_RUN_STATUS_LABELS: Record<AutomationStepRunStatus, string> = {
  pending: "Ожидает",
  success: "Успешно",
  skipped: "Пропущено",
  failed: "Ошибка",
};
