"use client";
import { useState } from "react";
import { ArrowDown, ArrowUp, Loader2, Plus, Trash2, X } from "lucide-react";

import { ApiError } from "@/lib/api-client";
import { T } from "@/lib/design-system";
import {
  useCreateAutomation,
  useUpdateAutomation,
} from "@/lib/hooks/use-automations";
import { useTemplates } from "@/lib/hooks/use-templates";
import type {
  AutomationAction,
  AutomationOut,
  AutomationStep,
  AutomationStepType,
  AutomationTrigger,
} from "@/lib/types";

import { ACTION_LABELS, STEP_TYPE_LABELS, TRIGGER_LABELS } from "./types";

// ---------------------------------------------------------------------------
// Editor modal
// ---------------------------------------------------------------------------

export function AutomationEditor({
  automation,
  onClose,
}: {
  automation: AutomationOut | null;
  onClose: () => void;
}) {
  const isEdit = automation !== null;
  const create = useCreateAutomation();
  const update = useUpdateAutomation(automation?.id ?? "");
  const templatesQuery = useTemplates();
  const templates = templatesQuery.data ?? [];

  const [name, setName] = useState(automation?.name ?? "");
  const [trigger, setTrigger] = useState<AutomationTrigger>(
    automation?.trigger ?? "stage_change",
  );
  const [actionType, setActionType] = useState<AutomationAction>(
    automation?.action_type ?? "send_template",
  );
  const [isActive, setIsActive] = useState(
    automation?.is_active ?? true,
  );

  // Action config — narrow per action_type. Only the relevant fields
  // are sent to the backend; the rest get ignored. Keeping all the
  // state up front simplifies the form even if a switch zeroes a
  // previously-typed field.
  const initialAC =
    (automation?.action_config_json ?? {}) as Record<string, unknown>;
  const [templateId, setTemplateId] = useState(
    typeof initialAC.template_id === "string" ? initialAC.template_id : "",
  );
  const [taskTitle, setTaskTitle] = useState(
    typeof initialAC.title === "string" ? initialAC.title : "",
  );
  const [dueInHours, setDueInHours] = useState(
    typeof initialAC.due_in_hours === "number"
      ? String(initialAC.due_in_hours)
      : "24",
  );
  const [targetStageId, setTargetStageId] = useState(
    typeof initialAC.target_stage_id === "string"
      ? initialAC.target_stage_id
      : "",
  );

  // Condition — v1 supports a simple {all: [{field, op, value}]} shape.
  // Frontend exposes one filter row to keep the surface small; the
  // backend already handles n-clause AND/OR.
  const initialFirstClause =
    (automation?.condition_json?.all?.[0] ?? null) as
      | { field?: string; op?: string; value?: unknown }
      | null;
  const [conditionField, setConditionField] = useState(
    typeof initialFirstClause?.field === "string"
      ? initialFirstClause.field
      : "",
  );
  const [conditionOp, setConditionOp] = useState(
    typeof initialFirstClause?.op === "string"
      ? initialFirstClause.op
      : "eq",
  );
  const [conditionValue, setConditionValue] = useState(
    initialFirstClause?.value !== undefined && initialFirstClause?.value !== null
      ? String(initialFirstClause.value)
      : "",
  );

  // Sprint 2.7 G2 — multi-step chain. Steps after the primary action
  // are stored on `automation.steps_json` from index 1 onward (step 0
  // is the primary action — kept as legacy for back-compat). UI shows
  // them as a list of «extra steps» under the action picker.
  const initialExtraSteps: AutomationStep[] = (() => {
    const stored = automation?.steps_json;
    if (!Array.isArray(stored) || stored.length <= 1) return [];
    return stored.slice(1).map((s) => ({
      type: (s.type as AutomationStepType) ?? "delay_hours",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      config: ((s.config as Record<string, any>) ?? {}) as Record<string, any>,
    }));
  })();
  const [extraSteps, setExtraSteps] = useState<AutomationStep[]>(initialExtraSteps);

  const [error, setError] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  function addExtraStep(type: AutomationStepType) {
    const defaultConfig: Record<string, unknown> =
      type === "delay_hours"
        ? { hours: 24 }
        : type === "create_task"
          ? { title: "", due_in_hours: 24 }
          : type === "send_template"
            ? { template_id: "" }
            : { target_stage_id: "" };
    setExtraSteps([...extraSteps, { type, config: defaultConfig }]);
  }

  function updateExtraStep(idx: number, patch: Partial<AutomationStep>) {
    setExtraSteps(
      extraSteps.map((s, i) =>
        i === idx
          ? {
              ...s,
              ...patch,
              config: { ...s.config, ...(patch.config ?? {}) },
            }
          : s,
      ),
    );
  }

  function removeExtraStep(idx: number) {
    setExtraSteps(extraSteps.filter((_, i) => i !== idx));
  }

  function moveExtraStep(idx: number, dir: -1 | 1) {
    const target = idx + dir;
    if (target < 0 || target >= extraSteps.length) return;
    const next = [...extraSteps];
    [next[idx], next[target]] = [next[target], next[idx]];
    setExtraSteps(next);
  }

  function buildPayload() {
    const action_config_json: Record<string, unknown> = {};
    if (actionType === "send_template") {
      action_config_json.template_id = templateId;
    } else if (actionType === "create_task") {
      action_config_json.title = taskTitle;
      const hrs = parseInt(dueInHours, 10);
      action_config_json.due_in_hours = Number.isFinite(hrs) ? hrs : 24;
    } else if (actionType === "move_stage") {
      action_config_json.target_stage_id = targetStageId;
    }

    const condition_json = conditionField
      ? {
          all: [
            {
              field: conditionField,
              op: conditionOp,
              value:
                conditionOp === "is_null" || conditionOp === "is_not_null"
                  ? null
                  : conditionValue,
            },
          ],
        }
      : null;

    // If the user added extra steps, materialise the full chain.
    // Step 0 = primary action (kept on `action_type` + `action_config_json`
    // for back-compat with single-step readers); steps 1+ are the
    // extras. Otherwise leave `steps_json: null` and the row fires as
    // a legacy single-action automation.
    const steps_json: AutomationStep[] | null =
      extraSteps.length > 0
        ? [
            { type: actionType as AutomationStepType, config: action_config_json },
            ...extraSteps,
          ]
        : null;

    return {
      name: name.trim(),
      trigger,
      trigger_config_json: null,
      condition_json,
      action_type: actionType,
      action_config_json,
      steps_json,
      is_active: isActive,
    };
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Название обязательно.");
      return;
    }
    if (actionType === "send_template" && !templateId) {
      setError("Выберите шаблон.");
      return;
    }
    if (actionType === "create_task" && !taskTitle.trim()) {
      setError("Заголовок задачи обязателен.");
      return;
    }
    if (actionType === "move_stage" && !targetStageId.trim()) {
      setError("Укажите ID целевой стадии.");
      return;
    }

    // Sprint 2.7 G2 — extra-steps validation. Match backend
    // `_validate_steps` so the form catches obvious problems before
    // a 400 round-trip.
    for (let i = 0; i < extraSteps.length; i++) {
      const s = extraSteps[i];
      if (s.type === "delay_hours") {
        const h = Number(s.config.hours);
        if (!Number.isFinite(h) || h <= 0 || h > 720) {
          setError(`Шаг ${i + 2}: пауза должна быть от 1 до 720 часов.`);
          return;
        }
      } else if (s.type === "send_template" && !s.config.template_id) {
        setError(`Шаг ${i + 2}: выберите шаблон.`);
        return;
      } else if (
        s.type === "create_task" &&
        !String(s.config.title ?? "").trim()
      ) {
        setError(`Шаг ${i + 2}: заголовок задачи обязателен.`);
        return;
      } else if (
        s.type === "move_stage" &&
        !String(s.config.target_stage_id ?? "").trim()
      ) {
        setError(`Шаг ${i + 2}: укажите ID стадии.`);
        return;
      }
    }

    const payload = buildPayload();
    const onErr = (err: ApiError) => {
      const detail =
        err.body && typeof err.body === "object"
          ? (err.body as { detail?: unknown }).detail
          : null;
      if (detail && typeof detail === "object" && "message" in detail) {
        setError(String((detail as { message: unknown }).message));
      } else {
        setError("Не удалось сохранить.");
      }
    };

    if (isEdit) {
      update.mutate(payload, { onSuccess: onClose, onError: onErr });
    } else {
      create.mutate(payload, { onSuccess: onClose, onError: onErr });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div className="bg-white rounded-card shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <h3 className="type-card-title">
            {isEdit ? "Редактировать автоматизацию" : "Новая автоматизация"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-brand-muted hover:text-brand-primary p-1"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="px-5 py-4 space-y-3">
          <div>
            <label className={`${T.mono} uppercase text-brand-muted`}>
              Название
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="При попадании в Pilot — отправить welcome"
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            />
          </div>

          <div>
            <label className={`${T.mono} uppercase text-brand-muted`}>
              Триггер
            </label>
            <select
              value={trigger}
              onChange={(e) =>
                setTrigger(e.target.value as AutomationTrigger)
              }
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            >
              {(Object.keys(TRIGGER_LABELS) as AutomationTrigger[]).map((t) => (
                <option key={t} value={t}>
                  {TRIGGER_LABELS[t]}
                </option>
              ))}
            </select>
          </div>

          <fieldset className="border border-brand-border rounded-xl p-3 space-y-2">
            <legend className={`px-1 ${T.mono} uppercase text-brand-muted`}>
              Условие (необязательно)
            </legend>
            <div className="grid grid-cols-3 gap-2">
              <select
                value={conditionField}
                onChange={(e) => setConditionField(e.target.value)}
                className="bg-brand-bg border border-brand-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
              >
                <option value="">— без условия —</option>
                <option value="priority">priority</option>
                <option value="score">score</option>
                <option value="deal_type">deal_type</option>
                <option value="source">source</option>
                <option value="assignment_status">assignment_status</option>
              </select>
              <select
                value={conditionOp}
                onChange={(e) => setConditionOp(e.target.value)}
                disabled={!conditionField}
                className="bg-brand-bg border border-brand-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 disabled:opacity-50"
              >
                <option value="eq">=</option>
                <option value="neq">≠</option>
                <option value="gte">≥</option>
                <option value="lte">≤</option>
                <option value="gt">&gt;</option>
                <option value="lt">&lt;</option>
                <option value="is_null">пусто</option>
                <option value="is_not_null">не пусто</option>
              </select>
              <input
                type="text"
                value={conditionValue}
                onChange={(e) => setConditionValue(e.target.value)}
                disabled={
                  !conditionField ||
                  conditionOp === "is_null" ||
                  conditionOp === "is_not_null"
                }
                placeholder="value"
                className="bg-brand-bg border border-brand-border rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 disabled:opacity-50"
              />
            </div>
          </fieldset>

          <div>
            <label className={`${T.mono} uppercase text-brand-muted`}>
              Действие
            </label>
            <select
              value={actionType}
              onChange={(e) =>
                setActionType(e.target.value as AutomationAction)
              }
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            >
              {(Object.keys(ACTION_LABELS) as AutomationAction[]).map((a) => (
                <option key={a} value={a}>
                  {ACTION_LABELS[a]}
                </option>
              ))}
            </select>
          </div>

          {actionType === "send_template" && (
            <div>
              <label className={`${T.mono} uppercase text-brand-muted`}>
                Шаблон
              </label>
              <select
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
              >
                <option value="">— выберите шаблон —</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.channel})
                  </option>
                ))}
              </select>
            </div>
          )}

          {actionType === "create_task" && (
            <>
              <div>
                <label className={`${T.mono} uppercase text-brand-muted`}>
                  Заголовок задачи
                </label>
                <input
                  type="text"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="Связаться с ЛПР"
                  className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                />
                <p className="text-xs text-brand-muted mt-1">
                  Поддерживает подстановки <code>{"{{lead.field}}"}</code>.
                </p>
              </div>
              <div>
                <label className={`${T.mono} uppercase text-brand-muted`}>
                  Срок (часов)
                </label>
                <input
                  type="number"
                  min="1"
                  value={dueInHours}
                  onChange={(e) => setDueInHours(e.target.value)}
                  className="mt-1 w-32 bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                />
              </div>
            </>
          )}

          {actionType === "move_stage" && (
            <div>
              <label className={`${T.mono} uppercase text-brand-muted`}>
                Целевая стадия (UUID)
              </label>
              <input
                type="text"
                value={targetStageId}
                onChange={(e) => setTargetStageId(e.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
                className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
              />
              <p className="text-xs text-brand-muted mt-1">
                ID можно скопировать из URL карточки стадии в /settings →
                Воронки.
              </p>
            </div>
          )}

          {/* Sprint 2.7 G2 — extra steps for a multi-step chain.
              Step 0 is the primary action above; these are scheduled
              after step 0 fires. Delay steps gate the next step's
              schedule (no side-effect of their own). */}
          <fieldset className="border border-brand-border rounded-xl p-3 space-y-2">
            <legend className={`px-1 ${T.mono} uppercase text-brand-muted`}>
              Цепочка после первого шага (необязательно)
            </legend>
            {extraSteps.length === 0 ? (
              <p className="text-xs text-brand-muted">
                Без шагов — автоматизация однократная (запускается один раз
                при срабатывании триггера).
              </p>
            ) : (
              <ul className="space-y-2">
                {extraSteps.map((step, idx) => (
                  <li
                    key={idx}
                    className="bg-brand-bg/60 border border-brand-border rounded-xl p-2 space-y-2"
                  >
                    <div className={`flex items-center gap-1.5 ${T.mono} text-brand-muted`}>
                      <span>Шаг {idx + 2}</span>
                      <select
                        value={step.type}
                        onChange={(e) =>
                          updateExtraStep(idx, {
                            type: e.target.value as AutomationStepType,
                            config:
                              e.target.value === "delay_hours"
                                ? { hours: 24 }
                                : e.target.value === "create_task"
                                  ? { title: "", due_in_hours: 24 }
                                  : e.target.value === "send_template"
                                    ? { template_id: "" }
                                    : { target_stage_id: "" },
                          })
                        }
                        className="ml-1 bg-white border border-brand-border rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                      >
                        {(Object.keys(STEP_TYPE_LABELS) as AutomationStepType[]).map(
                          (t) => (
                            <option key={t} value={t}>
                              {STEP_TYPE_LABELS[t]}
                            </option>
                          ),
                        )}
                      </select>
                      <div className="flex-1" />
                      <button
                        type="button"
                        onClick={() => moveExtraStep(idx, -1)}
                        disabled={idx === 0}
                        className="p-1 text-brand-muted hover:text-brand-primary disabled:opacity-30"
                        aria-label="Вверх"
                      >
                        <ArrowUp size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveExtraStep(idx, 1)}
                        disabled={idx === extraSteps.length - 1}
                        className="p-1 text-brand-muted hover:text-brand-primary disabled:opacity-30"
                        aria-label="Вниз"
                      >
                        <ArrowDown size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeExtraStep(idx)}
                        className="p-1 text-brand-muted hover:text-rose"
                        aria-label="Удалить шаг"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>

                    {step.type === "delay_hours" && (
                      <div>
                        <label className="text-xs text-brand-muted">
                          Часов:
                        </label>
                        <input
                          type="number"
                          min="1"
                          max="720"
                          value={String(step.config.hours ?? 24)}
                          onChange={(e) =>
                            updateExtraStep(idx, {
                              config: {
                                hours: parseInt(e.target.value, 10) || 1,
                              },
                            })
                          }
                          className="ml-2 w-24 bg-white border border-brand-border rounded-lg px-2 py-1 text-xs font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                        />
                        <span className="ml-2 text-xs text-brand-muted">
                          (1—720)
                        </span>
                      </div>
                    )}

                    {step.type === "send_template" && (
                      <select
                        value={String(step.config.template_id ?? "")}
                        onChange={(e) =>
                          updateExtraStep(idx, {
                            config: { template_id: e.target.value },
                          })
                        }
                        className="w-full bg-white border border-brand-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                      >
                        <option value="">— шаблон —</option>
                        {templates.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name} ({t.channel})
                          </option>
                        ))}
                      </select>
                    )}

                    {step.type === "create_task" && (
                      <div className="grid grid-cols-[1fr_auto] gap-2">
                        <input
                          type="text"
                          placeholder="Заголовок задачи"
                          value={String(step.config.title ?? "")}
                          onChange={(e) =>
                            updateExtraStep(idx, {
                              config: { title: e.target.value },
                            })
                          }
                          className="bg-white border border-brand-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                        />
                        <input
                          type="number"
                          min="1"
                          placeholder="часов"
                          value={String(step.config.due_in_hours ?? 24)}
                          onChange={(e) =>
                            updateExtraStep(idx, {
                              config: {
                                due_in_hours:
                                  parseInt(e.target.value, 10) || 24,
                              },
                            })
                          }
                          className="w-20 bg-white border border-brand-border rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                        />
                      </div>
                    )}

                    {step.type === "move_stage" && (
                      <input
                        type="text"
                        placeholder="UUID стадии"
                        value={String(step.config.target_stage_id ?? "")}
                        onChange={(e) =>
                          updateExtraStep(idx, {
                            config: { target_stage_id: e.target.value },
                          })
                        }
                        className="w-full bg-white border border-brand-border rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                      />
                    )}
                  </li>
                ))}
              </ul>
            )}
            <div className="flex items-center gap-1 flex-wrap pt-1">
              <button
                type="button"
                onClick={() => addExtraStep("delay_hours")}
                className="text-xs inline-flex items-center gap-1 px-2 py-1 rounded-full bg-brand-bg border border-brand-border hover:border-brand-accent"
              >
                <Plus size={10} /> Пауза
              </button>
              <button
                type="button"
                onClick={() => addExtraStep("send_template")}
                className="text-xs inline-flex items-center gap-1 px-2 py-1 rounded-full bg-brand-bg border border-brand-border hover:border-brand-accent"
              >
                <Plus size={10} /> Шаблон
              </button>
              <button
                type="button"
                onClick={() => addExtraStep("create_task")}
                className="text-xs inline-flex items-center gap-1 px-2 py-1 rounded-full bg-brand-bg border border-brand-border hover:border-brand-accent"
              >
                <Plus size={10} /> Задача
              </button>
              <button
                type="button"
                onClick={() => addExtraStep("move_stage")}
                className="text-xs inline-flex items-center gap-1 px-2 py-1 rounded-full bg-brand-bg border border-brand-border hover:border-brand-accent"
              >
                <Plus size={10} /> Стадия
              </button>
            </div>
          </fieldset>

          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded"
            />
            <span>Активна</span>
          </label>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="submit"
              disabled={pending}
              className="inline-flex items-center gap-1.5 bg-brand-accent text-white rounded-full px-4 py-2 text-sm font-semibold hover:bg-brand-accent/90 disabled:opacity-40 transition duration-300"
            >
              {pending && <Loader2 size={13} className="animate-spin" />}
              {isEdit ? "Сохранить" : "Создать"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="text-sm text-brand-muted hover:text-brand-primary"
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
