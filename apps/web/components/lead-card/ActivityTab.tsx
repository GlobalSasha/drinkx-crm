"use client";
import { useEffect, useState } from "react";
import {
  CheckSquare,
  Square,
  ChevronDown,
  Loader2,
  ArrowRight,
  ArrowLeft,
  ClipboardList,
} from "lucide-react";
import {
  useActivities,
  useCreateActivity,
  useCompleteTask,
} from "@/lib/hooks/use-activities";
import { useUpdateLead } from "@/lib/hooks/use-lead";
import { C } from "@/lib/design-system";
import type { ActivityOut, LeadOut } from "@/lib/types";

const FILTER_OPTIONS = [
  { label: "Все", value: "" },
  { label: "Комментарии", value: "comment" },
  { label: "Задачи", value: "task" },
  { label: "Звонки", value: "call" },
  { label: "Почта", value: "email" },
  { label: "Телеграм", value: "telegram" },
  { label: "Этапы", value: "stage_change" },
  { label: "Заявки", value: "form_submission" },
  { label: "Файлы", value: "file" },
];

const COMPOSER_MODES = ["comment", "task", "reminder", "file"] as const;
type ComposerMode = (typeof COMPOSER_MODES)[number];

const MODE_LABELS: Record<ComposerMode, string> = {
  comment: "Комментарий",
  task: "Задача",
  reminder: "Напоминание",
  file: "Файл",
};

interface Props {
  leadId: string;
  lead: LeadOut;
}

export function ActivityTab({ leadId, lead }: Props) {
  const [filterType, setFilterType] = useState("");
  const [mode, setMode] = useState<ComposerMode>("comment");

  // Composer state
  const [commentText, setCommentText] = useState("");
  const [taskName, setTaskName] = useState("");
  const [taskDueAt, setTaskDueAt] = useState("");
  const [reminderText, setReminderText] = useState("");
  const [reminderAt, setReminderAt] = useState("");
  const [fileUrl, setFileUrl] = useState("");
  const [fileKind, setFileKind] = useState("document");

  const activitiesQuery = useActivities(leadId, filterType || undefined);
  const createActivity = useCreateActivity(leadId);
  const completeTask = useCompleteTask(leadId);
  const updateLead = useUpdateLead(leadId);

  // Next-step block — moved here from the Deal tab. Writes to the
  // lead's `next_step` / `next_action_at` fields and mirrors the
  // commitment as a `task` activity so it shows up in the feed below.
  // `next_action_at` is the canonical column name; the spec used
  // `next_step_due_at` but no such field exists in LeadUpdate.
  const [nextStep, setNextStep] = useState(lead.next_step ?? "");
  const [nextStepDue, setNextStepDue] = useState(
    lead.next_action_at ? lead.next_action_at.slice(0, 16) : "",
  );
  const [savingNextStep, setSavingNextStep] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    setNextStep(lead.next_step ?? "");
    setNextStepDue(
      lead.next_action_at ? lead.next_action_at.slice(0, 16) : "",
    );
  }, [lead.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }

  async function handleSaveNextStep() {
    const trimmed = nextStep.trim();
    if (!trimmed || savingNextStep) return;
    setSavingNextStep(true);
    try {
      // 1. Persist on the lead.
      await updateLead.mutateAsync({
        next_step: trimmed,
        next_action_at: nextStepDue || null,
      });
      // 2. Mirror as a task activity so the commitment shows up in
      // the feed below — same shape as the inline «Задача» composer.
      await createActivity.mutateAsync({
        type: "task",
        payload_json: { name: trimmed },
        task_due_at: nextStepDue || null,
      });
      showToast("Следующий шаг сохранён");
    } catch {
      showToast("Не удалось сохранить");
    } finally {
      setSavingNextStep(false);
    }
  }

  const allItems: ActivityOut[] = activitiesQuery.data
    ? activitiesQuery.data.pages.flatMap((p) => p.items)
    : [];

  function handlePublish() {
    if (mode === "comment") {
      if (!commentText.trim()) return;
      createActivity.mutate(
        { type: "comment", payload_json: { text: commentText.trim() } },
        { onSuccess: () => setCommentText("") }
      );
    } else if (mode === "task") {
      if (!taskName.trim()) return;
      createActivity.mutate(
        {
          type: "task",
          payload_json: { name: taskName.trim() },
          task_due_at: taskDueAt || null,
        },
        { onSuccess: () => { setTaskName(""); setTaskDueAt(""); } }
      );
    } else if (mode === "reminder") {
      if (!reminderText.trim()) return;
      createActivity.mutate(
        {
          type: "reminder",
          payload_json: { text: reminderText.trim() },
          reminder_trigger_at: reminderAt || null,
        },
        { onSuccess: () => { setReminderText(""); setReminderAt(""); } }
      );
    } else if (mode === "file") {
      if (!fileUrl.trim()) return;
      createActivity.mutate(
        {
          type: "file",
          file_url: fileUrl.trim(),
          file_kind: fileKind,
          payload_json: {},
        },
        { onSuccess: () => { setFileUrl(""); } }
      );
    }
  }

  return (
    <div className="space-y-5">
      {/* Next step — pinned to the top of the activity tab. The
          commitment lives on the lead record AND mirrors itself as a
          task activity in the feed below for visibility. */}
      <div className="p-4 bg-brand-soft rounded-2xl border border-brand-accent/20">
        <p className={`${C.caption} text-brand-muted mb-3`}>следующий шаг</p>
        <input
          value={nextStep}
          onChange={(e) => setNextStep(e.target.value)}
          placeholder="Что делаем? (например: отправить КП)"
          className={`${C.form.field} mb-2`}
        />
        <div className="flex gap-2 items-center">
          <input
            type="datetime-local"
            value={nextStepDue}
            onChange={(e) => setNextStepDue(e.target.value)}
            className={`${C.form.field} flex-1`}
          />
          <button
            onClick={handleSaveNextStep}
            disabled={!nextStep.trim() || savingNextStep}
            className={`${C.button.primary} ${C.btnLg} px-4 py-2 disabled:opacity-40 shrink-0`}
          >
            {savingNextStep ? "..." : "Сохранить"}
          </button>
        </div>
      </div>

      {/* Composer */}
      <div className="bg-canvas rounded-2xl border border-black/5 p-4">
        {/* Mode tabs */}
        <div className="flex gap-0.5 mb-3 bg-white/60 rounded-lg p-0.5 w-fit">
          {COMPOSER_MODES.map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                mode === m
                  ? "bg-white text-ink shadow-soft"
                  : "text-muted-2 hover:text-ink"
              }`}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>

        {/* Comment */}
        {mode === "comment" && (
          <div className="space-y-2">
            <textarea
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Напишите комментарий..."
              rows={3}
              className="w-full px-3 py-2.5 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 resize-none transition-all"
            />
            <div className="flex justify-end">
              <button
                onClick={handlePublish}
                disabled={!commentText.trim() || createActivity.isPending}
                className="px-4 py-1.5 rounded-pill text-sm font-semibold bg-ink text-white hover:bg-ink/90 disabled:opacity-40 transition-all"
              >
                {createActivity.isPending ? "..." : "Опубликовать"}
              </button>
            </div>
          </div>
        )}

        {/* Task */}
        {mode === "task" && (
          <div className="space-y-2">
            <input
              type="text"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              placeholder="Название задачи..."
              className="w-full px-3 py-2.5 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
            />
            <input
              type="datetime-local"
              value={taskDueAt}
              onChange={(e) => setTaskDueAt(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
            />
            <div className="flex justify-end">
              <button
                onClick={handlePublish}
                disabled={!taskName.trim() || createActivity.isPending}
                className="px-4 py-1.5 rounded-pill text-sm font-semibold bg-ink text-white hover:bg-ink/90 disabled:opacity-40 transition-all"
              >
                {createActivity.isPending ? "..." : "Создать задачу"}
              </button>
            </div>
          </div>
        )}

        {/* Reminder */}
        {mode === "reminder" && (
          <div className="space-y-2">
            <input
              type="text"
              value={reminderText}
              onChange={(e) => setReminderText(e.target.value)}
              placeholder="Текст напоминания..."
              className="w-full px-3 py-2.5 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
            />
            <input
              type="datetime-local"
              value={reminderAt}
              onChange={(e) => setReminderAt(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
            />
            <div className="flex justify-end">
              <button
                onClick={handlePublish}
                disabled={!reminderText.trim() || createActivity.isPending}
                className="px-4 py-1.5 rounded-pill text-sm font-semibold bg-ink text-white hover:bg-ink/90 disabled:opacity-40 transition-all"
              >
                {createActivity.isPending ? "..." : "Создать"}
              </button>
            </div>
          </div>
        )}

        {/* File */}
        {mode === "file" && (
          <div className="space-y-2">
            <input
              type="url"
              value={fileUrl}
              onChange={(e) => setFileUrl(e.target.value)}
              placeholder="URL файла..."
              className="w-full px-3 py-2.5 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
            />
            <select
              value={fileKind}
              onChange={(e) => setFileKind(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
            >
              <option value="document">Документ</option>
              <option value="presentation">Презентация</option>
              <option value="contract">Договор</option>
              <option value="other">Другое</option>
            </select>
            <div className="flex justify-end">
              <button
                onClick={handlePublish}
                disabled={!fileUrl.trim() || createActivity.isPending}
                className="px-4 py-1.5 rounded-pill text-sm font-semibold bg-ink text-white hover:bg-ink/90 disabled:opacity-40 transition-all"
              >
                {createActivity.isPending ? "..." : "Прикрепить"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap gap-1">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilterType(opt.value)}
            className={`px-3 py-1 text-xs font-semibold rounded-pill transition-all ${
              filterType === opt.value
                ? "bg-ink text-white"
                : "bg-canvas text-muted hover:bg-canvas-2"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Feed */}
      {activitiesQuery.isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 size={20} className="animate-spin text-muted-2" />
        </div>
      ) : (
        <div className="space-y-2">
          {allItems.length === 0 && (
            <p className="text-sm text-muted-2 text-center py-6">
              Активностей нет
            </p>
          )}
          {allItems.map((activity) => (
            <ActivityItem
              key={activity.id}
              activity={activity}
              onCompleteTask={() => completeTask.mutate(activity.id)}
            />
          ))}
        </div>
      )}

      {/* Load more */}
      {activitiesQuery.hasNextPage && (
        <div className="flex justify-center">
          <button
            onClick={() => activitiesQuery.fetchNextPage()}
            disabled={activitiesQuery.isFetchingNextPage}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-muted hover:text-ink bg-canvas hover:bg-canvas-2 rounded-pill transition-all"
          >
            {activitiesQuery.isFetchingNextPage ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <ChevronDown size={14} />
            )}
            Загрузить ещё
          </button>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-ink text-white text-sm font-semibold px-5 py-2.5 rounded-pill shadow-soft z-50">
          {toast}
        </div>
      )}
    </div>
  );
}

function ActivityItem({
  activity,
  onCompleteTask,
}: {
  activity: ActivityOut;
  onCompleteTask: () => void;
}) {
  const date = new Date(activity.created_at);
  const dateStr = date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
  });
  const timeStr = date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });

  if (activity.type === "task") {
    return (
      <div
        className={`flex items-start gap-3 p-3 rounded-xl border transition-colors ${
          activity.task_done
            ? "bg-success/5 border-success/10"
            : "bg-canvas border-black/5"
        }`}
      >
        <button
          onClick={onCompleteTask}
          disabled={activity.task_done}
          className="mt-0.5 shrink-0"
        >
          {activity.task_done ? (
            <CheckSquare size={16} className="text-success" />
          ) : (
            <Square size={16} className="text-muted-2 hover:text-brand-accent transition-colors" />
          )}
        </button>
        <div className="flex-1 min-w-0">
          <p
            className={`text-sm font-medium ${
              activity.task_done ? "line-through text-muted-2" : "text-ink"
            }`}
          >
            {activity.payload_json?.name ?? "Задача"}
          </p>
          {activity.task_due_at && (
            <p className="text-xs text-muted-2 mt-0.5">
              Срок:{" "}
              {new Date(activity.task_due_at).toLocaleDateString("ru-RU")}
            </p>
          )}
          {activity.task_done && activity.task_completed_at && (
            <p className="text-xs text-success mt-0.5">
              Выполнено:{" "}
              {new Date(activity.task_completed_at).toLocaleDateString("ru-RU")}
            </p>
          )}
        </div>
        <span className="font-mono text-[10px] text-muted-3 shrink-0">
          {dateStr} {timeStr}
        </span>
      </div>
    );
  }

  if (activity.type === "email") {
    return <EmailActivityItem activity={activity} dateStr={dateStr} timeStr={timeStr} />;
  }

  if (activity.type === "form_submission") {
    const payload = (activity.payload_json ?? {}) as {
      form_name?: string;
      source_domain?: string;
      utm?: Record<string, string>;
    };
    const formName = payload.form_name ?? "Веб-форма";
    const sourceDomain = payload.source_domain || "";
    const utmSource = payload.utm?.utm_source || "";
    return (
      <div className="p-3 bg-canvas rounded-xl border border-black/5">
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <ClipboardList size={14} className="text-brand-accent shrink-0" />
            <span className="text-[10px] font-mono text-muted-3 uppercase tracking-wide">
              Заявка с формы
            </span>
          </div>
          <span className="font-mono text-[10px] text-muted-3 shrink-0">
            {dateStr} {timeStr}
          </span>
        </div>
        <p className="text-sm font-bold text-ink leading-snug break-words">
          {formName}
        </p>
        {sourceDomain && (
          <p className="mt-0.5 text-xs text-muted-2">
            Источник: <span className="font-mono">{sourceDomain}</span>
          </p>
        )}
        {utmSource && (
          <p className="mt-0.5 text-xs text-muted-2">
            Кампания: <span className="font-mono">{utmSource}</span>
          </p>
        )}
      </div>
    );
  }

  if (activity.type === "stage_change") {
    const payload = activity.payload_json ?? {};
    return (
      <div className="flex items-center gap-2 py-2 px-3 bg-canvas/50 rounded-xl border border-black/5">
        <span className="text-xs text-muted-2">
          {payload.from_stage ?? "—"}
        </span>
        <ArrowRight size={12} className="text-muted-3 shrink-0" />
        <span className="text-xs font-semibold text-ink">
          {payload.to_stage ?? "—"}
        </span>
        {payload.gate_skipped && (
          <span className="text-[10px] font-semibold text-rose bg-rose/10 px-1.5 py-0.5 rounded-pill ml-1">
            gate skipped
          </span>
        )}
        <span className="font-mono text-[10px] text-muted-3 ml-auto shrink-0">
          {dateStr} {timeStr}
        </span>
      </div>
    );
  }

  // Default: comment / reminder / file / other
  const text =
    activity.payload_json?.text ??
    activity.body ??
    activity.subject ??
    activity.file_url ??
    "";

  const TYPE_LABELS: Record<string, string> = {
    comment: "Комментарий",
    reminder: "Напоминание",
    file: "Файл",
    call: "Звонок",
    email: "Почта",
    telegram: "Telegram",
  };

  return (
    <div className="p-3 bg-canvas rounded-xl border border-black/5">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-mono text-muted-3">
          {TYPE_LABELS[activity.type] ?? activity.type}
        </span>
        <span className="font-mono text-[10px] text-muted-3">
          {dateStr} {timeStr}
        </span>
      </div>
      {text && <p className="text-sm text-ink leading-relaxed">{text}</p>}
      {activity.type === "file" && activity.file_url && (
        <a
          href={activity.file_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-brand-accent hover:underline"
        >
          {activity.file_kind ?? "Файл"}: {activity.file_url}
        </a>
      )}
    </div>
  );
}

// Email rendering — Sprint 2.0 G5. Same outer style as the default
// activity card, with a header line carrying direction icon + sender
// + timestamp, then bold subject, then body preview with expand toggle.
export function EmailActivityItem({
  activity,
  dateStr,
  timeStr,
}: {
  activity: ActivityOut;
  dateStr: string;
  timeStr: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const isInbound = activity.direction !== "outbound";
  const sender = activity.from_identifier ?? "—";
  const subject = activity.subject ?? "(без темы)";
  const body = activity.body ?? "";
  const hasBody = body.trim().length > 0;
  const isLong = body.length > 200;
  const preview = isLong ? body.slice(0, 200) + "…" : body;

  return (
    <div className="p-3 bg-canvas rounded-xl border border-black/5">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          {isInbound ? (
            <ArrowLeft size={12} className="text-blue-600 shrink-0" aria-label="Входящее" />
          ) : (
            <ArrowRight size={12} className="text-emerald-600 shrink-0" aria-label="Исходящее" />
          )}
          <span className="text-[11px] font-mono text-muted-2 truncate">{sender}</span>
        </div>
        <span className="font-mono text-[10px] text-muted-3 shrink-0">
          {dateStr} {timeStr}
        </span>
      </div>
      <p className="text-sm font-bold text-ink leading-snug break-words">{subject}</p>
      {hasBody && (
        <>
          <p className="mt-1 text-[13px] text-muted leading-relaxed whitespace-pre-wrap break-words">
            {expanded ? body : preview}
          </p>
          {isLong && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="mt-1.5 text-[11px] font-semibold text-brand-accent hover:underline inline-flex items-center gap-0.5"
            >
              {expanded ? "Свернуть" : "Показать полностью"}
              <ChevronDown
                size={12}
                className={`transition-transform ${expanded ? "rotate-180" : ""}`}
              />
            </button>
          )}
        </>
      )}
    </div>
  );
}
