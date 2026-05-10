"use client";

import { useEffect, useState } from "react";
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
import { C } from "@/lib/design-system";

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

// ─── Counter widget ────────────────────────────────────────

interface CounterProps {
  label: string;
  icon: React.ReactNode;
  value: number;
  note: string;
  accent?: boolean;
}

function CounterWidget({ label, icon, value, note, accent }: CounterProps) {
  const wrapBg = accent
    ? "bg-brand-soft border border-brand-accent/20"
    : "bg-white border border-brand-border";
  const valueColor = accent ? "text-brand-accent-text" : C.color.text;
  const iconColor = accent ? "text-brand-accent-text" : "text-brand-muted";
  return (
    <div className={`${wrapBg} rounded-[2rem] p-5 h-full flex flex-col gap-2`}>
      <div className="flex items-center gap-2">
        <span className={iconColor}>{icon}</span>
        <span
          className={`${C.bodyXs} ${C.color.mutedLight} uppercase tracking-wider font-medium`}
        >
          {label}
        </span>
      </div>
      <div className={`${C.metricSm} ${valueColor} tabular-nums leading-none`}>
        {value}
      </div>
      <div className={`${C.bodyXs} ${C.color.mutedLight}`}>{note}</div>
    </div>
  );
}

// ─── Focus / top-leads widget ─────────────────────────────

function FocusWidget() {
  // Realistic placeholder. Real wire-up: pull top-3 fit-scored leads
  // from useTopLeads() (TBD).
  const leads = [
    { name: "Coffee Lab Moscow",     segment: "HoReCa · Москва",     score: 92, tier: "A" },
    { name: "Brusnika QSR Network",  segment: "QSR · Екатеринбург", score: 88, tier: "A" },
    { name: "Nika Office Park",      segment: "Офисы · СПб",         score: 81, tier: "A" },
  ];
  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Фокус дня"
        subtitle="Чак рекомендует начать с этих лидов"
        icon={<Sparkles size={16} className="text-brand-accent" />}
      />
      <div className="flex flex-col gap-2 mt-4 flex-1">
        {leads.map((l) => (
          <div
            key={l.name}
            className="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-brand-bg"
          >
            <span className="bg-brand-accent text-white text-[10px] font-bold rounded-full w-6 h-6 flex items-center justify-center shrink-0">
              {l.tier}
            </span>
            <div className="min-w-0 flex-1">
              <p className={`${C.bodySm} font-semibold ${C.color.text} truncate`}>
                {l.name}
              </p>
              <p className={`${C.bodyXs} ${C.color.mutedLight} truncate`}>
                {l.segment}
              </p>
            </div>
            <span
              className={`${C.bodyXs} font-mono font-bold tabular-nums bg-brand-soft text-brand-accent-text px-2 py-0.5 rounded-full shrink-0`}
            >
              {l.score}
            </span>
            <ChevronRight size={14} className="text-brand-muted shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Task-list widget ──────────────────────────────────────

interface PlanRow {
  block: string;
  time: string;
  kind: "call" | "email" | "meeting";
  title: string;
  lead: string;
}

function TaskListWidget() {
  const tasks: PlanRow[] = [
    { block: "Утро",  time: "10:00", kind: "call",    title: "Уточнить дату пилота", lead: "Coffee Lab Moscow" },
    { block: "Утро",  time: "11:30", kind: "email",   title: "Отправить КП",          lead: "Brusnika QSR" },
    { block: "День",  time: "14:00", kind: "meeting", title: "Демо станции",          lead: "Nika Office Park" },
    { block: "Вечер", time: "17:30", kind: "call",    title: "Follow-up по пилоту",   lead: "Mintea Lab" },
  ];
  const kindIcon: Record<PlanRow["kind"], React.ReactNode> = {
    call:    <Phone size={13} />,
    email:   <Mail size={13} />,
    meeting: <Calendar size={13} />,
  };
  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Список задач"
        subtitle="Расставлено по таймблокам Чаком"
        icon={<ListChecks size={16} className="text-brand-muted" />}
      />
      <div className="flex flex-col gap-1.5 mt-4 flex-1">
        {tasks.map((t, i) => (
          <div
            key={i}
            className="flex items-center gap-3 px-3 py-2 rounded-2xl bg-brand-bg"
          >
            <span
              className={`${C.bodyXs} font-mono font-semibold uppercase tracking-wider ${C.color.mutedLight} w-12 shrink-0 tabular-nums`}
            >
              {t.time}
            </span>
            <span className="text-brand-muted shrink-0">{kindIcon[t.kind]}</span>
            <div className="min-w-0 flex-1">
              <p className={`${C.bodySm} font-semibold ${C.color.text} truncate`}>
                {t.title}
              </p>
              <p className={`${C.bodyXs} ${C.color.mutedLight} truncate`}>
                {t.lead}
              </p>
            </div>
            <CheckCircle2 size={14} className="text-brand-muted shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Чак insights widget ──────────────────────────────────

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
  const stages = [
    { name: "Новые",      count: 18, pct: 100 },
    { name: "Подогрев",   count: 14, pct: 78 },
    { name: "КП",         count:  9, pct: 50 },
    { name: "Переговоры", count:  5, pct: 28 },
    { name: "Пилот",      count:  3, pct: 17 },
  ];
  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Стадии воронки"
        subtitle="Распределение активных лидов"
        icon={<BarChart3 size={16} className="text-brand-muted" />}
      />
      <div className="flex flex-col gap-2.5 mt-4 flex-1">
        {stages.map((s) => (
          <div key={s.name} className="flex items-center gap-3">
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
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Notifications widget (full-width strip) ───────────────

function NotifWidget() {
  const notifs = [
    {
      text: "Чак обогатил лид Coffee Lab Moscow",
      time: "2 мин назад",
      tone: "accent",
    },
    {
      text: "Новая заявка с формы «Каталог»",
      time: "12 мин назад",
      tone: "neutral",
    },
    {
      text: "Brusnika QSR ответили на КП",
      time: "47 мин назад",
      tone: "neutral",
    },
    {
      text: "Чак напомнит о звонке с Mintea Lab в 17:30",
      time: "1 ч назад",
      tone: "accent",
    },
  ];
  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 h-full flex flex-col">
      <WidgetHeader
        title="Уведомления"
        subtitle="Что произошло сегодня"
        icon={<Bell size={16} className="text-brand-muted" />}
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 mt-4">
        {notifs.map((n, i) => {
          const dotColor =
            n.tone === "accent" ? "bg-brand-accent" : "bg-brand-muted";
          return (
            <div
              key={i}
              className="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-brand-bg"
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
              <p className={`${C.bodySm} ${C.color.text} truncate flex-1`}>
                {n.text}
              </p>
              <span
                className={`${C.bodyXs} font-mono ${C.color.mutedLight} shrink-0`}
              >
                {n.time}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Shared widget header ──────────────────────────────────

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
  const chakSummary = "Чак подготовил план · 7 задач на сегодня";

  function renderWidget(id: WidgetId) {
    switch (id) {
      case "w-tasks":
        return (
          <CounterWidget
            label="Задачи"
            icon={<ListChecks size={14} />}
            value={7}
            note="3 просрочено"
          />
        );
      case "w-followup":
        return (
          <CounterWidget
            label="Follow-up"
            icon={<AlarmClock size={14} />}
            value={4}
            note="требуют ответа"
            accent
          />
        );
      case "w-rotting":
        return (
          <CounterWidget
            label="Устаревает"
            icon={<Flame size={14} />}
            value={5}
            note="без движения 7+ дн"
          />
        );
      case "w-pipeline":
        return (
          <CounterWidget
            label="В воронке"
            icon={<BarChart3 size={14} />}
            value={43}
            note="активных лида"
          />
        );
      case "w-focus":
        return <FocusWidget />;
      case "w-tasklist":
        return <TaskListWidget />;
      case "w-chak":
        return <ChakWidget />;
      case "w-funnel":
        return <FunnelWidget />;
      case "w-notif":
        return <NotifWidget />;
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
