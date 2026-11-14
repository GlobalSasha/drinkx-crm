"use client";

// «Что дальше» — одна строка под шапкой карточки: ближайшая открытая задача
// лида со сроком. Ничего не вводится отдельно: шаг — это задача, которую
// менеджер и так ставит. Задач может быть много, шаг всегда один.
//
// Источник — тот же запрос, что у вкладки «Задачи» (`useLeadTasks`, общий
// кеш). Сервер отдаёт открытые первыми, по сроку, без срока — в конце, так
// что первая строка выборки и есть ближайший шаг.
import { AlertCircle, ArrowRight, Plus } from "lucide-react";

import { useLeadTasks } from "@/lib/hooks/use-lead-tasks";
import { C } from "@/lib/design-system";

interface Props {
  leadId: string;
  /** Владелец лида: имя исполнителя показываем, только если задача не у него. */
  ownerId: string | null;
  onPlanTask: () => void;
}

const DAY_MS = 86_400_000;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function daysWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "дня";
  return "дней";
}

/** Срок задачи словами и признак просрочки. */
export function describeDue(
  iso: string | null,
  now: Date = new Date(),
): { label: string; overdue: boolean } {
  if (!iso) return { label: "без срока", overdue: false };
  const due = new Date(iso);
  const dayDiff = Math.round((startOfDay(due) - startOfDay(now)) / DAY_MS);
  if (due.getTime() < now.getTime()) {
    const late = -dayDiff;
    if (late <= 0) return { label: "просрочено сегодня", overdue: true };
    return { label: `просрочено на ${late} ${daysWord(late)}`, overdue: true };
  }
  if (dayDiff === 0) return { label: "сегодня", overdue: false };
  if (dayDiff === 1) return { label: "завтра", overdue: false };
  const dd = String(due.getDate()).padStart(2, "0");
  const mm = String(due.getMonth() + 1).padStart(2, "0");
  return { label: `до ${dd}.${mm}`, overdue: false };
}

export function NextStepLine({ leadId, ownerId, onPlanTask }: Props) {
  const { items, counts, isPending, isError } = useLeadTasks(leadId);

  // Пока грузится или не загрузилось — молчим, чтобы не мигать «нет шага».
  if (isPending || isError) return null;

  const next = items[0] && !items[0].task_done ? items[0] : null;

  if (!next) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-3 px-4 py-2 rounded-lg bg-brand-bg">
        <span className="inline-flex items-center gap-2 type-label text-brand-muted">
          <AlertCircle size={14} aria-hidden />
          Нет следующего шага
        </span>
        <button
          type="button"
          onClick={onPlanTask}
          className={`inline-flex items-center gap-1 h-7 px-3 rounded-full bg-white border border-brand-border type-label text-brand-primary hover:border-brand-accent transition-colors ${C.focusRing}`}
        >
          <Plus size={12} aria-hidden />
          Поставить задачу
        </button>
      </div>
    );
  }

  const due = describeDue(next.task_due_at);
  const more = Math.max(0, (counts?.open ?? 1) - 1);
  const otherAssignee =
    next.assignee_user_id && next.assignee_user_id !== ownerId
      ? next.assignee_name
      : null;

  return (
    <div className="mt-3 flex items-center gap-3 px-4 py-2 rounded-lg bg-brand-bg min-w-0">
      <ArrowRight size={14} className="shrink-0 text-brand-muted" aria-hidden />
      <div className="min-w-0 flex-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="type-label text-brand-muted">Что дальше</span>
        <span className="min-w-0 type-body text-brand-primary truncate" title={next.text}>
          {next.text}
        </span>
      </div>
      <span
        className={`shrink-0 type-label whitespace-nowrap ${due.overdue ? "text-rose" : "text-brand-muted-strong"}`}
      >
        {due.label}
      </span>
      {otherAssignee && (
        <span className="hidden sm:inline shrink-0 type-label text-brand-muted whitespace-nowrap">
          {otherAssignee}
        </span>
      )}
      {more > 0 && (
        <span className="shrink-0 type-label text-brand-muted whitespace-nowrap">
          ещё {more}
        </span>
      )}
    </div>
  );
}
