"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ListChecks,
  AlarmClock,
  Flame,
  BarChart3,
  GripVertical,
  X,
  Plus,
  LayoutGrid,
  Sparkles,
  Bell,
  TrendingUp,
  ChevronRight,
  Phone,
  Mail,
  Calendar,
  CheckCircle2,
  ArrowUpRight,
  Check,
} from "lucide-react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { User } from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import { C } from "@/lib/design-system";
import { api } from "@/lib/api-client";
import { useTodayPlan } from "@/lib/hooks/use-daily-plan";
import { useFollowupsPending } from "@/lib/hooks/use-followups";
import { useLeads } from "@/lib/hooks/use-leads";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { useNotificationsList, useMarkRead } from "@/lib/hooks/use-notifications";
import { relativeTime } from "@/lib/relative-time";
import type { LeadOut, Priority, TaskKind, TimeBlock } from "@/lib/types";

// ─── Widget registry ────────────────────────────────────────

type WidgetId =
  | "w-tasks"
  | "w-followup"
  | "w-rotting"
  | "w-pipeline"
  | "w-focus"
  | "w-tasklist"
  | "w-chak"
  | "w-funnel"
  | "w-notif";

const DEFAULT_ORDER: WidgetId[] = [
  "w-tasks",
  "w-followup",
  "w-rotting",
  "w-pipeline",
  "w-focus",
  "w-tasklist",
  "w-chak",
  "w-funnel",
  "w-notif",
];

const WIDGET_LABELS: Record<WidgetId, string> = {
  "w-tasks":    "Задачи",
  "w-followup": "Follow-up",
  "w-rotting":  "Устаревает",
  "w-pipeline": "В воронке",
  "w-focus":    "Фокус дня",
  "w-tasklist": "Список задач",
  "w-chak":     "Инсайты Чака",
  "w-funnel":   "Стадии воронки",
  "w-notif":    "Уведомления",
};

// Grid spans per widget. Counter widgets are 1 column on the auto-fit
// grid; main widgets occupy 2; the notifications strip stretches across.
const WIDGET_SPAN: Record<WidgetId, string> = {
  "w-tasks":    "",
  "w-followup": "",
  "w-rotting":  "",
  "w-pipeline": "",
  "w-focus":    "sm:col-span-2",
  "w-tasklist": "sm:col-span-2",
  "w-chak":     "sm:col-span-2",
  "w-funnel":   "sm:col-span-2",
  "w-notif":    "col-span-full",
};

// Single shared filter object for `useLeads`. TanStack Query dedupes
// identical query keys, so the four widgets that consume this share
// one network request.
const TODAY_LEADS_FILTER = { page_size: 200 } as const;

// DailyPlanItem only exposes a coarse `time_block`. To render a clock-time
// in the task list we map each block to a representative hour and combine
// it with the plan's `plan_date` to synthesise an ISO datetime.
const TIME_BLOCK_HOUR: Record<TimeBlock, number> = {
  morning:   9,
  midday:    12,
  afternoon: 15,
  evening:   18,
};

function buildPlanItemDueAt(
  planDate: string | undefined,
  timeBlock: TimeBlock | null,
): string | null {
  if (!planDate || !timeBlock) return null;
  const d = new Date(`${planDate}T00:00:00`);
  d.setHours(TIME_BLOCK_HOUR[timeBlock], 0, 0, 0);
  return d.toISOString();
}

function formatTaskTime(due_at: string | null): string {
  if (!due_at) return "—";
  const d = new Date(due_at);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const isTomorrow =
    d.toDateString() === new Date(today.getTime() + 86400000).toDateString();

  const time = d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
  if (isToday) return time;
  if (isTomorrow) return `завтра ${time}`;
  return (
    d.toLocaleDateString("ru", { day: "numeric", month: "short" }) + " " + time
  );
}

const TASK_KIND_ICON: Record<TaskKind, React.ReactNode> = {
  call:      <Phone size={13} />,
  email:     <Mail size={13} />,
  meeting:   <Calendar size={13} />,
  research:  <Sparkles size={13} />,
  follow_up: <AlarmClock size={13} />,
};

// Priority A is the strongest signal; D weakest. Used as a tiebreaker
// after `score` for the focus-of-the-day ordering.
const PRIORITY_RANK: Record<Priority, number> = { A: 4, B: 3, C: 2, D: 1 };

function leadFocusSortKey(l: LeadOut): number {
  // Higher value = earlier. score is 0..100; priority adds up to 5
  // points so it nudges ties without overpowering.
  return l.score + (l.priority ? PRIORITY_RANK[l.priority] : 0);
}

// ─── Greeting ──────────────────────────────────────────────

function getGreeting(name: string) {
  const h = new Date().getHours();
  if (h >= 5 && h < 12) return { text: `Доброе утро, ${name}`, icon: "🌅" };
  if (h >= 12 && h < 17) return { text: `Добрый день, ${name}`, icon: "☀️" };
  if (h >= 17 && h < 22) return { text: `Добрый вечер, ${name}`, icon: "🌆" };
  return { text: `Доброй ночи, ${name}`, icon: "🌙" };
}

function getDateLabel() {
  const d = new Date();
  const weekday = d.toLocaleDateString("ru-RU", { weekday: "long" });
  const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  return {
    weekday: weekday[0].toUpperCase() + weekday.slice(1),
    date,
  };
}

// ─── Shared UI primitives ──────────────────────────────────

/** Generic skeleton block — `animate-pulse bg-brand-panel rounded-lg`. */
function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-brand-panel rounded-lg ${className}`} />;
}

interface CounterProps {
  label: string;
  icon: React.ReactNode;
  value: number | null;
  note: string;
  accent?: boolean;
  loading?: boolean;
}

function CounterWidget({ label, icon, value, note, accent, loading }: CounterProps) {
  const wrapBg = accent
    ? "bg-brand-soft border border-brand-accent/20"
    : "bg-white border border-brand-border";
  const valueColor = accent ? "text-brand-accent-text" : C.color.text;
  const iconColor = accent ? "text-brand-accent-text" : "text-brand-muted";
  return (
    <div
      className={`${wrapBg} rounded-[2rem] p-5 h-full flex flex-col items-center text-center gap-2`}
    >
      <div className="flex items-center gap-2">
        <span className={iconColor}>{icon}</span>
        <span
          className={`${C.bodyXs} ${C.color.mutedLight} uppercase tracking-wider font-medium`}
        >
          {label}
        </span>
      </div>
      {loading ? (
        <Skeleton className="h-10 w-20" />
      ) : (
        <div className={`${C.metricSm} ${valueColor} tabular-nums leading-none`}>
          {value ?? "—"}
        </div>
      )}
      <div className={`${C.bodyXs} ${C.color.mutedLight}`}>{note}</div>
    </div>
  );
}

/** Title + optional subtitle row used by every non-counter widget. */
function WidgetHeader({
  title,
  subtitle,
  icon,
  accent,
}: {
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  accent?: boolean;
}) {
  const titleColor = accent ? "text-brand-accent-text" : C.color.text;
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {icon}
          <h3 className={`${C.bodySm} font-bold ${titleColor}`}>{title}</h3>
        </div>
        {subtitle && (
          <p className={`${C.bodyXs} ${C.color.mutedLight} mt-0.5`}>
            {subtitle}
          </p>
        )}
      </div>
      <ArrowUpRight size={14} className={`${C.color.mutedLight} mt-0.5 shrink-0`} />
    </div>
  );
}

// ─── Counter wrappers (data-aware) ─────────────────────────

function TasksCounter() {
  const { data, isLoading, isError } = useTodayPlan();
  const items = data?.items ?? [];
  const total = items.length;
  const undone = items.filter((i) => !i.done).length;
  // DailyPlanItem has no `overdue` flag and no due-time — count
  // undone items as the «остаётся» metric so the widget still
  // communicates urgency without inventing data.
  const note = isError
    ? "—"
    : total === 0
      ? "пока пусто"
      : undone === 0
        ? "всё выполнено"
        : `${undone} ${pluralRu(undone, ["осталась", "остались", "осталось"])}`;
  return (
    <CounterWidget
      label="Задачи"
      icon={<ListChecks size={14} />}
      value={isError ? null : total}
      note={note}
      loading={isLoading}
    />
  );
}

function FollowupCounter() {
  const { data, isLoading, isError } = useFollowupsPending();
  const pending = data?.pending_count ?? 0;
  const overdue = data?.overdue_count ?? 0;
  const note = isError
    ? "—"
    : pending === 0
      ? "никто не ждёт ответа"
      : overdue > 0
        ? `${overdue} ${pluralRu(overdue, ["просрочен", "просрочено", "просрочено"])}`
        : "требуют ответа";
  return (
    <CounterWidget
      label="Follow-up"
      icon={<AlarmClock size={14} />}
      value={isError ? null : pending}
      note={note}
      accent
      loading={isLoading}
    />
  );
}

function RottingCounter() {
  const { data, isLoading, isError } = useLeads(TODAY_LEADS_FILTER);
  const leads = data?.items ?? [];
  const count = leads.filter(
    (l) => l.assignment_status === "assigned" && l.is_rotting_stage,
  ).length;
  const note = isError
    ? "—"
    : count === 0
      ? "движение в норме"
      : "без движения 7+ дн";
  return (
    <CounterWidget
      label="Устаревает"
      icon={<Flame size={14} />}
      value={isError ? null : count}
      note={note}
      loading={isLoading}
    />
  );
}

function PipelineCounter() {
  const { data, isLoading, isError } = useLeads(TODAY_LEADS_FILTER);
  const leads = data?.items ?? [];
  const count = leads.filter((l) => l.assignment_status === "assigned").length;
  const note = isError
    ? "—"
    : count === 0
      ? "пока ничего"
      : `${pluralRu(count, ["активный лид", "активных лида", "активных лидов"])}`;
  return (
    <CounterWidget
      label="В воронке"
      icon={<BarChart3 size={14} />}
      value={isError ? null : count}
      note={note}
      loading={isLoading}
    />
  );
}

// ─── Focus widget ─────────────────────────────────────────

function FocusWidget() {
  const { data, isLoading, isError } = useLeads(TODAY_LEADS_FILTER);
  const top = useMemo(() => {
    const leads = (data?.items ?? []).filter(
      (l) => l.assignment_status === "assigned",
    );
    return [...leads]
      .sort((a, b) => leadFocusSortKey(b) - leadFocusSortKey(a))
      .slice(0, 4);
  }, [data]);
  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Фокус дня"
        subtitle="Чак рекомендует начать с этих лидов"
        icon={<Sparkles size={16} className="text-brand-accent" />}
      />
      <div className="flex flex-col gap-2 mt-4 flex-1">
        {isLoading && (
          <>
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </>
        )}
        {!isLoading && isError && (
          <p className={`${C.bodyXs} ${C.color.mutedLight}`}>—</p>
        )}
        {!isLoading && !isError && top.length === 0 && (
          <p className={`${C.bodySm} ${C.color.mutedLight}`}>
            Нет лидов в работе
          </p>
        )}
        {!isLoading && !isError && top.map((l) => (
          <Link
            key={l.id}
            href={`/leads/${l.id}`}
            className="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-brand-bg cursor-pointer"
          >
            {l.priority && (
              <span className="bg-brand-accent text-white text-[10px] font-bold rounded-full w-6 h-6 flex items-center justify-center shrink-0">
                {l.priority}
              </span>
            )}
            <div className="min-w-0 flex-1">
              <p className={`${C.bodySm} font-semibold ${C.color.text} truncate`}>
                {l.company_name}
              </p>
              <p className={`${C.bodyXs} ${C.color.mutedLight} truncate`}>
                {[l.segment, l.city].filter(Boolean).join(" · ") || "—"}
              </p>
            </div>
            <span
              className={`${C.bodyXs} font-mono font-bold tabular-nums bg-brand-soft text-brand-accent-text px-2 py-0.5 rounded-full shrink-0`}
            >
              {l.score}
            </span>
            <ChevronRight size={14} className="text-brand-muted shrink-0" />
          </Link>
        ))}
      </div>
    </div>
  );
}

// ─── Task-list widget ──────────────────────────────────────

const TASKS_PER_PAGE = 4;

function TaskListWidget() {
  const { data, isLoading, isError } = useTodayPlan();
  const { data: leadsData } = useLeads(TODAY_LEADS_FILTER);
  const qc = useQueryClient();
  const planDate = data?.plan_date;

  const items = useMemo(() => {
    const all = data?.items ?? [];
    return [...all].sort((a, b) => a.position - b.position);
  }, [data]);

  // Default target lead for the inline quick-add — same ranking as the
  // FocusWidget so what the user sees in Focus is what gets the new task.
  const focusLead = useMemo(() => {
    const leads = (leadsData?.items ?? []).filter(
      (l) => l.assignment_status === "assigned",
    );
    if (leads.length === 0) return null;
    return [...leads].sort(
      (a, b) => leadFocusSortKey(b) - leadFocusSortKey(a),
    )[0];
  }, [leadsData]);

  const [taskPage, setTaskPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(items.length / TASKS_PER_PAGE));
  // Clamp the page when items shrink (e.g. after refetch) so we don't
  // render an empty slice.
  const safePage = Math.min(taskPage, totalPages - 1);
  const visibleTasks = items.slice(
    safePage * TASKS_PER_PAGE,
    (safePage + 1) * TASKS_PER_PAGE,
  );

  const [addingTask, setAddingTask] = useState(false);
  const [newTaskText, setNewTaskText] = useState("");

  const addTask = useMutation({
    mutationFn: ({ leadId, name }: { leadId: string; name: string }) =>
      api.post(`/leads/${leadId}/activities`, {
        type: "task",
        payload_json: { name },
        task_due_at: new Date().toISOString(),
      }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
      qc.invalidateQueries({ queryKey: ["activities", vars.leadId] });
      setNewTaskText("");
      setAddingTask(false);
    },
  });

  function handleAddTask() {
    const name = newTaskText.trim();
    if (!name || !focusLead || addTask.isPending) return;
    addTask.mutate({ leadId: focusLead.id, name });
  }

  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      {/* Inline header — replaces the shared WidgetHeader so the
          up-right arrow can be a Link instead of a static icon. */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ListChecks size={16} className="text-brand-muted" />
            <h3 className={`${C.bodySm} font-bold ${C.color.text}`}>
              Список задач
            </h3>
          </div>
          <p className={`${C.bodyXs} ${C.color.mutedLight} mt-0.5`}>
            Расставлено по таймблокам Чаком
          </p>
        </div>
        <Link
          href="/today?tab=tasks"
          title="Все задачи"
          aria-label="Открыть все задачи"
          className={`${C.color.mutedLight} mt-0.5 shrink-0`}
        >
          <ArrowUpRight size={14} />
        </Link>
      </div>

      <div className="flex flex-col gap-1.5 mt-4 flex-1">
        {isLoading && (
          <>
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </>
        )}
        {!isLoading && isError && (
          <p className={`${C.bodyXs} ${C.color.mutedLight}`}>—</p>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <p className={`${C.bodySm} ${C.color.mutedLight}`}>
            На сегодня задач нет
          </p>
        )}
        {!isLoading && !isError && visibleTasks.map((t) => {
          const taskTitle = t.hint_one_liner || "Задача";
          const due = buildPlanItemDueAt(planDate, t.time_block);
          const rowClass =
            "flex items-center gap-3 px-3 py-2 rounded-2xl bg-brand-bg";
          const inner = (
            <>
              <span
                className={`${C.bodyXs} ${C.color.mutedLight} uppercase tracking-wide tabular-nums w-16 shrink-0`}
              >
                {formatTaskTime(due)}
              </span>
              <span className="text-brand-muted shrink-0">
                {TASK_KIND_ICON[t.task_kind]}
              </span>
              <div className="min-w-0 flex-1">
                <p
                  className={`${C.bodySm} font-medium ${C.color.text} truncate max-w-[280px] ${
                    t.done ? "line-through opacity-60" : ""
                  }`}
                  title={taskTitle}
                >
                  {taskTitle}
                </p>
                <p
                  className={`${C.bodyXs} ${C.color.mutedLight} truncate max-w-[280px]`}
                  title={t.lead_company_name ?? undefined}
                >
                  {t.lead_company_name ?? "—"}
                </p>
              </div>
              <CheckCircle2
                size={14}
                className={t.done ? "text-success" : "text-brand-muted"}
              />
            </>
          );
          // Daily-plan items can have a null lead_id (general / standalone
          // tasks). Render those as a non-clickable row so we don't link
          // to a broken `/leads/null` route.
          return t.lead_id ? (
            <Link
              key={t.id}
              href={`/leads/${t.lead_id}?tab=activity&task=${t.id}`}
              className={`${rowClass} cursor-pointer`}
            >
              {inner}
            </Link>
          ) : (
            <div key={t.id} className={rowClass}>
              {inner}
            </div>
          );
        })}

        {/* Quick add: trigger button or inline form. Hidden while
            initial data is loading or errored so we don't render
            controls without context. */}
        {!isLoading && !isError && (
          addingTask ? (
            <div className="mt-2 flex gap-2 items-center">
              <input
                autoFocus
                value={newTaskText}
                onChange={(e) => setNewTaskText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newTaskText.trim()) handleAddTask();
                  if (e.key === "Escape") {
                    setAddingTask(false);
                    setNewTaskText("");
                  }
                }}
                placeholder={
                  focusLead
                    ? `Задача для ${focusLead.company_name}…`
                    : "Название задачи…"
                }
                disabled={addTask.isPending}
                className={`flex-1 ${C.form.field} py-2 text-sm`}
              />
              <button
                onClick={handleAddTask}
                disabled={
                  !newTaskText.trim() || !focusLead || addTask.isPending
                }
                aria-label="Сохранить задачу"
                className={`${C.button.primary} ${C.btn} px-3 py-2 disabled:opacity-40`}
              >
                <Check size={14} />
              </button>
              <button
                onClick={() => {
                  setAddingTask(false);
                  setNewTaskText("");
                }}
                aria-label="Отменить"
                className={`${C.button.ghost} ${C.btn} px-3 py-2`}
              >
                <X size={14} />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setAddingTask(true)}
              disabled={!focusLead}
              title={focusLead ? undefined : "Нет лида для привязки"}
              className={`w-full mt-2 py-2 rounded-xl border border-dashed border-brand-border text-brand-muted ${C.bodySm} flex items-center justify-center gap-1 disabled:opacity-40`}
            >
              <Plus size={12} aria-hidden /> добавить задачу
            </button>
          )
        )}
      </div>

      {/* Pagination dots — only when there's more than one page. */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1.5 mt-3 pt-3 border-t border-brand-border">
          {Array.from({ length: totalPages }).map((_, i) => (
            <button
              key={i}
              onClick={() => setTaskPage(i)}
              aria-label={`Страница ${i + 1}`}
              className={`h-1.5 rounded-full transition-all ${
                i === safePage ? "bg-brand-accent w-4" : "bg-brand-border w-1.5"
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Чак insights widget — mock for now ────────────────────

function ChakWidget() {
  const insights = [
    {
      icon: <Sparkles size={14} className="text-brand-accent" />,
      text: "3 лида готовы к закрытию — score выше 85, нет блокеров",
    },
    {
      icon: <TrendingUp size={14} className="text-brand-accent" />,
      text: "Конверсия из «Подогрев» в «КП» выросла на 18% за неделю",
    },
    {
      icon: <Flame size={14} className="text-brand-accent" />,
      text: "Coffee Lab Moscow — 5 дней без касания, рекомендую напомнить",
    },
  ];
  return (
    <div className="bg-brand-soft border border-brand-accent/20 rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Инсайты от Чака"
        subtitle="Что Чак заметил в твоих лидах сегодня"
        icon={<Sparkles size={16} className="text-brand-accent-text" />}
        accent
      />
      <div className="flex flex-col gap-2.5 mt-4 flex-1">
        {insights.map((it, i) => (
          <div key={i} className="flex items-start gap-3">
            <span className="mt-0.5 shrink-0">{it.icon}</span>
            <p className={`${C.bodySm} ${C.color.text} leading-snug`}>
              {it.text}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Funnel widget ─────────────────────────────────────────

function FunnelWidget() {
  const { data: pipelines, isLoading: pipelinesLoading, isError: pipelinesError } =
    usePipelines();
  const { data: leadsData, isLoading: leadsLoading, isError: leadsError } =
    useLeads(TODAY_LEADS_FILTER);
  const isLoading = pipelinesLoading || leadsLoading;
  const isError = pipelinesError || leadsError;

  const stages = useMemo(() => {
    const firstPipeline = pipelines?.[0];
    if (!firstPipeline)
      return [] as { id: string; name: string; count: number; pct: number }[];
    const visible = firstPipeline.stages.filter((s) => !s.is_won && !s.is_lost);
    const leads = leadsData?.items ?? [];
    const counts = visible.map((s) => ({
      id: s.id,
      name: s.name,
      count: leads.filter(
        (l) => l.assignment_status === "assigned" && l.stage_id === s.id,
      ).length,
    }));
    const max = Math.max(1, ...counts.map((c) => c.count));
    return counts.map((c) => ({ ...c, pct: Math.round((c.count / max) * 100) }));
  }, [pipelines, leadsData]);

  const visibleStages = stages.slice(0, 6);

  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Стадии воронки"
        subtitle="Распределение активных лидов"
        icon={<BarChart3 size={16} className="text-brand-muted" />}
      />
      <div className="flex flex-col gap-2.5 mt-4 flex-1">
        {isLoading && (
          <>
            <Skeleton className="h-5" />
            <Skeleton className="h-5" />
            <Skeleton className="h-5" />
            <Skeleton className="h-5" />
          </>
        )}
        {!isLoading && isError && (
          <p className={`${C.bodyXs} ${C.color.mutedLight}`}>—</p>
        )}
        {!isLoading && !isError && visibleStages.length === 0 && (
          <p className={`${C.bodySm} ${C.color.mutedLight}`}>
            Воронка ещё не настроена
          </p>
        )}
        {!isLoading && !isError && visibleStages.map((s) => (
          <Link
            key={s.id}
            href={`/pipeline?stage=${s.id}`}
            className="flex items-center gap-3 cursor-pointer"
          >
            <span
              className={`${C.bodyXs} ${C.color.mutedLight} w-24 shrink-0 truncate`}
            >
              {s.name}
            </span>
            <div className="flex-1 h-2 bg-brand-bg rounded-full overflow-hidden">
              <div
                className="h-full bg-brand-accent rounded-full transition-all duration-500"
                style={{ width: `${s.pct}%` }}
              />
            </div>
            <span
              className={`${C.bodyXs} font-mono font-bold tabular-nums ${C.color.text} w-6 text-right shrink-0`}
            >
              {s.count}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

// ─── Notifications widget (full-width strip) ───────────────

function NotifWidget() {
  const { data, isLoading, isError } = useNotificationsList({ unread: false });
  const markRead = useMarkRead();
  const items = useMemo(() => (data?.items ?? []).slice(0, 4), [data]);
  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Уведомления"
        subtitle="Что произошло сегодня"
        icon={<Bell size={16} className="text-brand-muted" />}
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 mt-4">
        {isLoading && (
          <>
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </>
        )}
        {!isLoading && isError && (
          <p className={`${C.bodyXs} ${C.color.mutedLight} col-span-full`}>—</p>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <p className={`${C.bodySm} ${C.color.mutedLight} col-span-full`}>
            Уведомлений пока нет
          </p>
        )}
        {!isLoading && !isError && items.map((n) => {
          const isUnread = n.read_at == null;
          const dotColor = isUnread ? "bg-brand-accent" : "bg-brand-muted";
          // Lead-bound notifications open the lead; everything else
          // (system, daily-plan-ready, etc.) goes to the full feed.
          const href = n.lead_id ? `/leads/${n.lead_id}` : "/notifications";
          return (
            <Link
              key={n.id}
              href={href}
              onClick={() => {
                if (isUnread) markRead.mutate(n.id);
              }}
              className="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-brand-bg cursor-pointer"
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
              <p className={`${C.bodySm} ${C.color.text} truncate flex-1`}>
                {n.title || n.body || "—"}
              </p>
              <span
                className={`${C.bodyXs} font-mono ${C.color.mutedLight} shrink-0`}
              >
                {relativeTime(n.created_at)}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

// ─── Sortable wrapper ──────────────────────────────────────

interface SortableWidgetProps {
  id: WidgetId;
  editing: boolean;
  onHide: () => void;
  spanClassName: string;
  children: React.ReactNode;
}

function SortableWidget({
  id,
  editing,
  onHide,
  spanClassName,
  children,
}: SortableWidgetProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} className={`relative ${spanClassName}`}>
      {editing && (
        <>
          <button
            {...attributes}
            {...listeners}
            className="absolute top-3 right-10 z-20 w-6 h-6 rounded-full bg-brand-panel flex items-center justify-center cursor-grab active:cursor-grabbing"
            aria-label="Переместить виджет"
          >
            <GripVertical size={12} className="text-brand-muted" />
          </button>
          <button
            onClick={onHide}
            className="absolute top-3 right-3 z-20 w-6 h-6 rounded-full bg-brand-panel flex items-center justify-center"
            aria-label="Скрыть виджет"
          >
            <X size={12} className="text-brand-muted" />
          </button>
        </>
      )}
      {children}
    </div>
  );
}

// ─── Russian pluralisation helper ──────────────────────────

/** Pick the right Russian plural form (1, 2-4, 5+) for a count. */
function pluralRu(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}

// ─── Page ──────────────────────────────────────────────────

export default function TodayPage() {
  const [user, setUser] = useState<User | null>(null);
  const [order, setOrder] = useState<WidgetId[]>(DEFAULT_ORDER);
  const [hidden, setHidden] = useState<Set<WidgetId>>(new Set());
  const [editing, setEditing] = useState(false);
  // Track when localStorage has been hydrated so we don't overwrite
  // saved layout with the initial defaults during the persistence
  // effect below.
  const [hydrated, setHydrated] = useState(false);

  // Load Supabase user — same pattern AppShell uses for displayName.
  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    supabase.auth.getUser().then(({ data }) => setUser(data.user));
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  const userId = user?.id ?? "anon";
  const firstName =
    (user?.user_metadata?.full_name as string | undefined)?.split(" ")[0] ??
    user?.email?.split("@")[0] ??
    "коллега";

  // Pull the today plan once at the page level so the Чак subline
  // can include the live task count without re-fetching.
  const { data: plan } = useTodayPlan();
  const todayTotal = plan?.items?.length ?? 0;

  // Load saved layout from localStorage. Runs whenever userId changes
  // (e.g. after auth resolves).
  useEffect(() => {
    try {
      const saved = localStorage.getItem(`today_widgets_${userId}`);
      if (saved) {
        const parsed = JSON.parse(saved) as {
          order?: WidgetId[];
          hidden?: WidgetId[];
        };
        // Validate against the current widget catalog so removed/renamed
        // ids don't sneak back in from old layouts.
        const validIds = new Set(DEFAULT_ORDER);
        const filteredOrder = parsed.order?.filter((id) =>
          validIds.has(id),
        ) ?? [];
        // Append any new widgets that were added since the save —
        // otherwise they'd never appear for users with old layouts.
        const missing = DEFAULT_ORDER.filter((id) => !filteredOrder.includes(id));
        setOrder([...filteredOrder, ...missing]);
        setHidden(new Set(parsed.hidden?.filter((id) => validIds.has(id)) ?? []));
      } else {
        setOrder(DEFAULT_ORDER);
        setHidden(new Set());
      }
    } catch {
      // Corrupt entry — fall back to defaults.
      setOrder(DEFAULT_ORDER);
      setHidden(new Set());
    }
    setHydrated(true);
  }, [userId]);

  // Persist on change, but only after the initial load has completed.
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(
        `today_widgets_${userId}`,
        JSON.stringify({ order, hidden: [...hidden] }),
      );
    } catch {
      // Quota exceeded or storage disabled — silently skip.
    }
  }, [order, hidden, userId, hydrated]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      setOrder((prev) =>
        arrayMove(
          prev,
          prev.indexOf(active.id as WidgetId),
          prev.indexOf(over.id as WidgetId),
        ),
      );
    }
  }

  function hideWidget(id: WidgetId) {
    setHidden((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }

  function showWidget(id: WidgetId) {
    setHidden((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }

  const greeting = getGreeting(firstName);
  const { weekday, date } = getDateLabel();
  const visible = order.filter((id) => !hidden.has(id));

  // Live subtitle. Uses task count when the plan resolves; falls back
  // to a generic line otherwise so the header doesn't twitch on slow
  // connections.
  const chakSummary =
    todayTotal > 0
      ? `Чак подготовил план · ${todayTotal} ${pluralRu(todayTotal, ["задача", "задачи", "задач"])} на сегодня`
      : "Чак готовит план на сегодня";

  function renderWidget(id: WidgetId) {
    switch (id) {
      case "w-tasks":
        return (
          <Link href="/today?tab=tasks" className="block h-full cursor-pointer">
            <TasksCounter />
          </Link>
        );
      case "w-followup":
        return (
          <Link
            href="/pipeline?filter=followup_overdue"
            className="block h-full cursor-pointer"
          >
            <FollowupCounter />
          </Link>
        );
      case "w-rotting":
        return (
          <Link
            href="/pipeline?filter=rotting"
            className="block h-full cursor-pointer"
          >
            <RottingCounter />
          </Link>
        );
      case "w-pipeline":
        return (
          <Link href="/pipeline" className="block h-full cursor-pointer">
            <PipelineCounter />
          </Link>
        );
      case "w-focus":    return <FocusWidget />;
      case "w-tasklist": return <TaskListWidget />;
      case "w-chak":     return <ChakWidget />;
      case "w-funnel":   return <FunnelWidget />;
      case "w-notif":    return <NotifWidget />;
    }
  }

  return (
    <div className="font-sans bg-canvas min-h-screen">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Header */}
        <div className="flex flex-wrap justify-between items-start gap-4 mb-6">
          <div className="min-w-0">
            <h1 className={`${C.h3} ${C.color.text} flex items-center gap-2`}>
              <span aria-hidden>{greeting.icon}</span>
              <span>{greeting.text}</span>
            </h1>
            <p className={`${C.bodySm} ${C.color.mutedLight} mt-1`}>
              {weekday}, {date} · {chakSummary}
            </p>
          </div>
          <button
            onClick={() => setEditing((v) => !v)}
            className={`${C.button.ghost} ${C.btnLg} px-4 py-2 inline-flex items-center gap-2`}
          >
            <LayoutGrid size={14} aria-hidden />
            {editing ? "Готово" : "Настроить"}
          </button>
        </div>

        {/* Edit-mode hint */}
        {editing && (
          <div
            className={`${C.bodyXs} ${C.color.mutedLight} mb-3 px-1`}
            role="status"
          >
            Перетащи виджет за рукоять, чтобы поменять порядок. Крестик — скрыть.
          </div>
        )}

        {/* Grid */}
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={visible} strategy={rectSortingStrategy}>
            <div
              className="grid gap-3"
              style={{
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              }}
            >
              {visible.map((id) => (
                <SortableWidget
                  key={id}
                  id={id}
                  editing={editing}
                  onHide={() => hideWidget(id)}
                  spanClassName={WIDGET_SPAN[id]}
                >
                  {renderWidget(id)}
                </SortableWidget>
              ))}
            </div>
          </SortableContext>
        </DndContext>

        {/* Hidden-widgets restore panel */}
        {editing && hidden.size > 0 && (
          <div className="border border-dashed border-brand-border rounded-[2rem] p-4 mt-4">
            <p className={`${C.bodySm} ${C.color.mutedLight} mb-3`}>
              Скрытые виджеты — нажми, чтобы вернуть
            </p>
            <div className="flex flex-wrap gap-2">
              {[...hidden].map((id) => (
                <button
                  key={id}
                  onClick={() => showWidget(id)}
                  className={`${C.button.ghost} ${C.btn} px-3 py-1.5 inline-flex items-center gap-1`}
                >
                  <Plus size={12} aria-hidden />
                  {WIDGET_LABELS[id]}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
