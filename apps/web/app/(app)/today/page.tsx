"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ListChecks,
  Flame,
  BarChart3,
  GripVertical,
  X,
  Plus,
  LayoutGrid,
  Bell,
  ArrowUpRight,
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
import type { User } from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { C } from "@/lib/design-system";
import { useLeads } from "@/lib/hooks/use-leads";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { useNotificationsList, useMarkRead } from "@/lib/hooks/use-notifications";
import { useMyTasks, useCompleteMyTask } from "@/lib/hooks/use-my-tasks";
import { relativeTime } from "@/lib/relative-time";
import { TaskTable } from "@/components/tasks/TaskTable";
import { RemindersWidget } from "@/components/today/RemindersWidget";
import { myTaskToRow, isOverdue, isToday, type TaskRow } from "@/lib/tasks";

// ─── Widget registry ────────────────────────────────────────

type WidgetId =
  | "w-rotting"
  | "w-pipeline"
  | "w-tasklist"
  | "w-reminders"
  | "w-funnel"
  | "w-notif";

const DEFAULT_ORDER: WidgetId[] = [
  "w-rotting",
  "w-pipeline",
  "w-tasklist",
  "w-reminders",
  "w-funnel",
  "w-notif",
];

const WIDGET_LABELS: Record<WidgetId, string> = {
  "w-rotting":   "Устаревает",
  "w-pipeline":  "В воронке",
  "w-tasklist":  "Список задач",
  "w-reminders": "Напоминания",
  "w-funnel":    "Стадии воронки",
  "w-notif":     "Уведомления",
};

// Uniform spans: every widget takes 2 columns on xl (4-col grid) and 2
// columns on sm (2-col grid). Counters share row 1, big widgets pair off,
// notif sits in a 2-col slot too. Uniform sizing means any reorder still
// packs without gaps, and @dnd-kit's rectSortingStrategy stays stable.
//
// The four content widgets also carry a shared `xl:min-h` floor so they
// render at the same height once they sit side-by-side at xl — combined
// with the grid's row-stretch (no `items-start`) every block lines up.
const BIG_WIDGET_MIN_H = "xl:min-h-[26rem]";
const WIDGET_SPAN: Record<WidgetId, string> = {
  "w-rotting":   "sm:col-span-1 xl:col-span-2",
  "w-pipeline":  "sm:col-span-1 xl:col-span-2",
  "w-tasklist":  `sm:col-span-2 xl:col-span-2 ${BIG_WIDGET_MIN_H}`,
  "w-reminders": `sm:col-span-2 xl:col-span-2 ${BIG_WIDGET_MIN_H}`,
  "w-funnel":    `sm:col-span-2 xl:col-span-2 ${BIG_WIDGET_MIN_H}`,
  "w-notif":     `sm:col-span-2 xl:col-span-2 ${BIG_WIDGET_MIN_H}`,
};

// Single shared filter object for `useLeads`. TanStack Query dedupes
// identical query keys, so the widgets that consume this share one
// network request.
const TODAY_LEADS_FILTER = { page_size: 200 } as const;

// ─── Greeting ──────────────────────────────────────────────

function getGreeting() {
  const h = new Date().getHours();
  if (h >= 5 && h < 12) return "Доброе утро";
  if (h >= 12 && h < 18) return "Добрый день";
  if (h >= 18) return "Добрый вечер";
  return "Доброй ночи";
}

function getDateTimeCaption() {
  const d = new Date();
  const weekday = d.toLocaleDateString("ru-RU", { weekday: "long" });
  const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return `${weekday}, ${date} · ${time}`;
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
  // Horizontal layout: label-and-note column on the left, big number on the
  // right. Keeps the card balanced whether it sits in a narrow 1-col cell
  // (mobile) or a wide 2-col cell (xl).
  return (
    <div
      className={`${wrapBg} rounded-[2rem] p-5 h-full flex items-center justify-between gap-4`}
    >
      <div className="min-w-0 flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className={iconColor}>{icon}</span>
          <span
            className={`text-sm ${C.color.mutedLight} uppercase tracking-wider font-semibold`}
          >
            {label}
          </span>
        </div>
        <div className={`type-caption ${C.color.mutedLight}`}>{note}</div>
      </div>
      {loading ? (
        <Skeleton className="h-10 w-16 shrink-0" />
      ) : (
        <div className={`type-kpi-number ${valueColor} shrink-0 tabular-nums`}>
          {value ?? "—"}
        </div>
      )}
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
          <h3 className={`type-caption font-bold italic ${titleColor}`}>{title}</h3>
        </div>
        {subtitle && (
          <p className={`type-caption ${C.color.mutedLight} mt-0.5`}>
            {subtitle}
          </p>
        )}
      </div>
      <ArrowUpRight size={14} className={`${C.color.mutedLight} mt-0.5 shrink-0`} />
    </div>
  );
}

// ─── Counter wrappers (data-aware) ─────────────────────────

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

// ─── Task-list widget (table) ──────────────────────────────

type PeriodFilter = "all" | "today" | "overdue";

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1 rounded-full type-caption font-semibold transition-colors ${
        active
          ? "bg-brand-accent text-white"
          : "bg-brand-panel text-brand-muted-strong hover:bg-brand-border"
      }`}
    >
      {children}
    </button>
  );
}

function TaskListWidget() {
  const { data, isLoading, isError } = useMyTasks();
  const completeTask = useCompleteMyTask();

  const allRows: TaskRow[] = useMemo(
    () => (data ?? []).map(myTaskToRow),
    [data],
  );

  const [period, setPeriod] = useState<PeriodFilter>("all");

  // Client-side filtering only — no extra API calls.
  const rows = useMemo(
    () =>
      allRows.filter((r) => {
        if (period === "today" && !isToday(r.due)) return false;
        if (period === "overdue" && !isOverdue(r)) return false;
        return true;
      }),
    [allRows, period],
  );

  const doneCount = allRows.filter((r) => r.done).length;
  const totalCount = allRows.length;
  const progressPct =
    totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

  function handleComplete(row: TaskRow) {
    if (!row.done && !completeTask.isPending)
      completeTask.mutate({ leadId: row.leadId, taskId: row.id });
  }

  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <ListChecks size={16} className="text-brand-muted" />
          <h3 className={`type-caption font-bold italic ${C.color.text}`}>
            Список задач
          </h3>
        </div>
        <Link
          href="/tasks"
          className="inline-flex items-center gap-1 type-caption font-semibold text-brand-accent-text hover:underline shrink-0"
        >
          Все задачи <ArrowUpRight size={13} />
        </Link>
      </div>

      {/* Progress */}
      {totalCount > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <div className="flex-1 h-1.5 rounded-full bg-brand-bg overflow-hidden">
            <div
              className="h-full rounded-full bg-brand-accent transition-all"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="type-caption font-mono tabular-nums text-brand-muted shrink-0">
            {doneCount} из {totalCount} выполнено
          </span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mt-4">
        <FilterChip active={period === "all"} onClick={() => setPeriod("all")}>
          Все
        </FilterChip>
        <FilterChip active={period === "today"} onClick={() => setPeriod("today")}>
          Сегодня
        </FilterChip>
        <FilterChip
          active={period === "overdue"}
          onClick={() => setPeriod("overdue")}
        >
          Просрочено
        </FilterChip>
      </div>

      {/* Table */}
      <div className="mt-3 flex-1">
        {isLoading && (
          <div className="flex flex-col gap-1.5">
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
          </div>
        )}
        {!isLoading && isError && (
          <p className={`type-caption ${C.color.mutedLight}`}>—</p>
        )}
        {!isLoading && !isError && (
          <TaskTable
            rows={rows}
            onComplete={handleComplete}
            isCompleting={completeTask.isPending}
            emptyText={
              allRows.length === 0
                ? "Задач пока нет"
                : "Нет задач под фильтр"
            }
          />
        )}
      </div>

      {/* Tasks are created inside a lead card («Задачи» tab), never here —
          a task must belong to a lead. A standalone-tasks block is a
          separate sprint. */}
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
      return [] as {
        id: string;
        name: string;
        count: number;
        pctOfTotal: number;
        pctOfMax: number;
      }[];
    const visible = firstPipeline.stages.filter((s) => !s.is_won && !s.is_lost);
    const leads = leadsData?.items ?? [];
    const counts = visible.map((s) => ({
      id: s.id,
      name: s.name,
      count: leads.filter(
        (l) => l.assignment_status === "assigned" && l.stage_id === s.id,
      ).length,
    }));
    const total = counts.reduce((acc, c) => acc + c.count, 0);
    const max = Math.max(1, ...counts.map((c) => c.count));
    return counts.map((c) => ({
      ...c,
      // Bar width uses % of max so the largest stage fills the row (visual rhythm).
      pctOfMax: Math.round((c.count / max) * 100),
      // Label uses % of total so the user reads actual distribution (the meaningful number).
      pctOfTotal: total > 0 ? Math.round((c.count / total) * 100) : 0,
    }));
  }, [pipelines, leadsData]);

  const visibleStages = stages.slice(0, 6);

  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Стадии воронки"
        subtitle="Распределение активных лидов"
        icon={<BarChart3 size={16} className="text-brand-muted" />}
      />
      <div className="flex flex-col gap-2.5 mt-6 flex-1">
        {isLoading && (
          <>
            <Skeleton className="h-5" />
            <Skeleton className="h-5" />
            <Skeleton className="h-5" />
            <Skeleton className="h-5" />
          </>
        )}
        {!isLoading && isError && (
          <p className={`type-caption ${C.color.mutedLight}`}>—</p>
        )}
        {!isLoading && !isError && visibleStages.length === 0 && (
          <p className={`type-caption ${C.color.mutedLight}`}>
            Воронка ещё не настроена
          </p>
        )}
        {!isLoading && !isError && visibleStages.map((s, index) => (
          <Link
            key={s.id}
            href={`/pipeline?stage=${s.id}`}
            className="flex items-center gap-3 cursor-pointer"
          >
            <span
              className={`type-caption ${C.color.mutedLight} w-28 shrink-0 leading-tight line-clamp-2`}
            >
              {s.name}
            </span>
            <div className="flex-1 h-2 bg-brand-bg rounded-full overflow-hidden">
              <div
                className="h-full bg-brand-accent rounded-full transition-all duration-700 ease-out"
                style={{
                  width: `${s.pctOfMax}%`,
                  transitionDelay: `${index * 80}ms`,
                }}
              />
            </div>
            <span
              className={`type-caption font-mono font-bold tabular-nums ${C.color.text} w-10 text-right shrink-0`}
            >
              {s.count}
            </span>
            <span
              className={`type-caption tabular-nums ${C.color.mutedLight} w-10 text-right shrink-0`}
            >
              {s.pctOfTotal}%
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 mt-6">
        {isLoading && (
          <>
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </>
        )}
        {!isLoading && isError && (
          <p className={`type-caption ${C.color.mutedLight} col-span-full`}>—</p>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <p className={`type-caption ${C.color.mutedLight} col-span-full`}>
            Уведомлений пока нет
          </p>
        )}
        {!isLoading && !isError && items.map((n) => {
          const isUnread = n.read_at == null;
          const dotColor = isUnread ? "bg-brand-accent" : "bg-brand-muted";
          return (
            <Link
              key={n.id}
              href={n.lead_id ? `/leads/${n.lead_id}` : "/today"}
              onClick={() => {
                if (isUnread) markRead.mutate(n.id);
              }}
              className="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-brand-bg cursor-pointer"
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
              <p className={`type-caption ${C.color.text} truncate flex-1`}>
                {n.title || n.body || "—"}
              </p>
              <span
                className={`type-caption font-mono ${C.color.mutedLight} shrink-0`}
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
  // In edit mode the whole card becomes the drag handle (the corner grip
  // is too small to find), and an overlay swallows clicks on inner Links
  // so they don't navigate or start an HTML5 drag of the <a> element that
  // would race the PointerSensor.
  const dragProps = editing ? { ...attributes, ...listeners } : {};
  return (
    <div
      id={id}
      ref={setNodeRef}
      style={style}
      className={`relative ${spanClassName} ${editing ? "cursor-grab active:cursor-grabbing" : ""}`}
      {...dragProps}
    >
      {editing && (
        <>
          {/* Click/drag shield over the whole card — blocks <a>-native drag
              and prevents Link navigation while editing. */}
          <div
            className="absolute inset-0 z-10"
            onClick={(e) => e.preventDefault()}
            onDragStart={(e) => e.preventDefault()}
            aria-hidden
          />
          <span
            className="absolute top-3 right-10 z-20 w-6 h-6 rounded-full bg-brand-panel flex items-center justify-center pointer-events-none"
            aria-hidden
          >
            <GripVertical size={12} className="text-brand-muted" />
          </span>
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
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
  // `useSearchParams` (deep-link `?tab=tasks` reader) bails the page
  // out of static rendering unless it sits under a Suspense boundary.
  return (
    <Suspense fallback={null}>
      <TodayPageInner />
    </Suspense>
  );
}

function TodayPageInner() {
  const [user, setUser] = useState<User | null>(null);
  const [order, setOrder] = useState<WidgetId[]>(DEFAULT_ORDER);
  const [hidden, setHidden] = useState<Set<WidgetId>>(new Set());
  const [editing, setEditing] = useState(false);
  const [hydrated, setHydrated] = useState(false);

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

  // Deep-link support: `/today?tab=tasks` scrolls the task-list widget
  // into view.
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  useEffect(() => {
    if (tabParam !== "tasks") return;
    const el = document.getElementById("w-tasklist");
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [tabParam]);

  // Load saved layout from localStorage.
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
        const missing = DEFAULT_ORDER.filter((id) => !filteredOrder.includes(id));
        setOrder([...filteredOrder, ...missing]);
        setHidden(new Set(parsed.hidden?.filter((id) => validIds.has(id)) ?? []));
      } else {
        setOrder(DEFAULT_ORDER);
        setHidden(new Set());
      }
    } catch {
      setOrder(DEFAULT_ORDER);
      setHidden(new Set());
    }
    setHydrated(true);
  }, [userId]);

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

  const greetingText = getGreeting();
  const dateTimeCaption = getDateTimeCaption();
  const visible = order.filter((id) => !hidden.has(id));

  const chakSummary = "Ваши задачи и клиенты на сегодня";

  function renderWidget(id: WidgetId) {
    switch (id) {
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
      case "w-tasklist":  return <TaskListWidget />;
      case "w-reminders": return <RemindersWidget />;
      case "w-funnel":    return <FunnelWidget />;
      case "w-notif":     return <NotifWidget />;
    }
  }

  return (
    <div className={pageContainerVariants({ width: "wide" })}>
      {/* Header */}
      <div className="bg-white border border-brand-border border-l-[3px] border-l-brand-accent rounded-[2rem] p-6 mb-6">
          <div className="type-caption text-brand-muted">{dateTimeCaption}</div>
          <h1 className={`type-page-title ${C.color.text} mt-1`}>
            {greetingText}, <span className="text-brand-accent">{firstName}</span>
          </h1>
          <p className={`type-caption ${C.color.mutedLight} mt-1`}>
            {chakSummary}
          </p>
        </div>

        {/* Configure row */}
        <div className="flex justify-end mb-4">
          <button
            onClick={() => setEditing((v) => !v)}
            className={`${C.button.ghost} type-body px-4 py-2 inline-flex items-center gap-2`}
          >
            <LayoutGrid size={14} aria-hidden />
            {editing ? "Готово" : "Настроить"}
          </button>
        </div>

        {/* Edit-mode hint */}
        {editing && (
          <div
            className={`type-caption ${C.color.mutedLight} mb-3 px-1`}
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
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 items-stretch">
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
            <p className={`type-caption ${C.color.mutedLight} mb-3`}>
              Скрытые виджеты — нажми, чтобы вернуть
            </p>
            <div className="flex flex-wrap gap-2">
              {[...hidden].map((id) => (
                <button
                  key={id}
                  onClick={() => showWidget(id)}
                  className={`${C.button.ghost} type-body px-3 py-1.5 inline-flex items-center gap-1`}
                >
                  <Plus size={12} aria-hidden />
                  {WIDGET_LABELS[id]}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
  );
}
