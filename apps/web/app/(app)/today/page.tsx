"use client";
import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Search, AlertTriangle, Clock } from "lucide-react";
import { useTodayLeads } from "@/lib/hooks/use-leads";
import { SprintModal } from "@/components/pipeline/SprintModal";
import type { LeadOut, Priority } from "@/lib/types";

// ---- Date helpers ----

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function groupKey(iso: string | null): "today" | "tomorrow" | "week" | "nodate" {
  if (!iso) return "nodate";
  const now = startOfDay(new Date());
  const date = startOfDay(new Date(iso));
  const diffDays = Math.round((date.getTime() - now.getTime()) / 86_400_000);
  if (diffDays <= 0) return "today";
  if (diffDays === 1) return "tomorrow";
  if (diffDays <= 7) return "week";
  return "week"; // show beyond 7 days still in "this week" bucket
}

function relativeLabel(iso: string | null): string {
  if (!iso) return "—";
  const now = new Date();
  const date = new Date(iso);
  const diffMs = date.getTime() - now.getTime();
  const diffDays = Math.round(diffMs / 86_400_000);

  if (diffDays < 0) {
    const overdue = Math.abs(diffDays);
    return `просрочено ${overdue} ${pluralDays(overdue)}`;
  }
  if (diffDays === 0) {
    const hours = date.getHours().toString().padStart(2, "0");
    const mins = date.getMinutes().toString().padStart(2, "0");
    return `сегодня в ${hours}:${mins}`;
  }
  if (diffDays === 1) return "завтра";
  return `через ${diffDays} ${pluralDays(diffDays)}`;
}

function pluralDays(n: number): string {
  if (n % 10 === 1 && n % 100 !== 11) return "день";
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return "дня";
  return "дней";
}

const TODAY_LABEL = new Date().toLocaleDateString("ru-RU", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

// ---- Priority badge styles ----

const PRIORITY_STYLES: Record<Priority, string> = {
  A: "bg-accent/10 text-accent",
  B: "bg-success/10 text-success",
  C: "bg-warning/10 text-warning",
  D: "bg-black/5 text-muted",
};

// ---- Filters ----

const PRIORITIES: Priority[] = ["A", "B", "C", "D"];

// ---- Components ----

function LeadRow({ lead }: { lead: LeadOut }) {
  const router = useRouter();
  const isRotting = lead.is_rotting_stage || lead.is_rotting_next_step;

  return (
    <div
      onClick={() => router.push(`/leads/${lead.id}`)}
      className="flex items-center justify-between gap-4 px-4 py-3 bg-white border border-black/5 rounded-xl hover:shadow-soft hover:-translate-y-0.5 transition-all duration-300 cursor-pointer group"
    >
      {/* Left: company info */}
      <div className="flex items-start gap-3 min-w-0">
        {isRotting && (
          <AlertTriangle size={14} className="text-warning shrink-0 mt-0.5" />
        )}
        <div className="min-w-0">
          <p className="font-semibold text-sm text-ink truncate leading-snug">
            {lead.company_name}
          </p>
          {(lead.segment || lead.city) && (
            <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-2 truncate mt-0.5">
              {[lead.segment, lead.city].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
      </div>

      {/* Middle: badges */}
      <div className="flex items-center gap-1.5 shrink-0">
        {lead.priority && (
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md ${PRIORITY_STYLES[lead.priority]}`}>
            {lead.priority}
          </span>
        )}
        {lead.deal_type && (
          <span className="text-[10px] font-mono bg-black/5 text-muted px-1.5 py-0.5 rounded-md">
            {lead.deal_type}
          </span>
        )}
        {isRotting && (
          <span className="text-[10px] font-mono flex items-center gap-0.5 text-warning">
            <Clock size={10} />
            rot
          </span>
        )}
      </div>

      {/* Right: next action */}
      <div className="text-xs font-mono text-muted-2 shrink-0 text-right min-w-[90px]">
        {relativeLabel(lead.next_action_at)}
      </div>
    </div>
  );
}

function Section({ title, leads }: { title: string; leads: LeadOut[] }) {
  if (leads.length === 0) return null;
  return (
    <div className="mb-6">
      <h2 className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-2 mb-2 px-1">
        {title} · {leads.length}
      </h2>
      <div className="flex flex-col gap-2">
        {leads.map((l) => <LeadRow key={l.id} lead={l} />)}
      </div>
    </div>
  );
}

// ---- Page ----

export default function TodayPage() {
  const { sorted, isLoading, isError } = useTodayLeads();
  const [sprintOpen, setSprintOpen] = useState(false);
  const [priorityFilter, setPriorityFilter] = useState<Priority | null>(null);
  const [search, setSearch] = useState("");

  // Local filter: priority + fuzzy search on company_name
  const filtered = useMemo(() => {
    return sorted.filter((l) => {
      if (priorityFilter && l.priority !== priorityFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!l.company_name.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [sorted, priorityFilter, search]);

  // Group
  const groups = useMemo(() => {
    const today: LeadOut[] = [];
    const tomorrow: LeadOut[] = [];
    const week: LeadOut[] = [];
    const nodate: LeadOut[] = [];
    for (const l of filtered) {
      const g = groupKey(l.next_action_at);
      if (g === "today") today.push(l);
      else if (g === "tomorrow") tomorrow.push(l);
      else if (g === "week") week.push(l);
      else nodate.push(l);
    }
    return { today, tomorrow, week, nodate };
  }, [filtered]);

  const total = filtered.length;
  const isEmpty = sorted.length === 0 && !isLoading;

  return (
    <>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b border-black/5 px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-extrabold tracking-tight">Сегодня</h1>
            <span className="font-mono text-[11px] text-muted-2 lowercase">{TODAY_LABEL}</span>
          </div>
          <span className="bg-black/5 text-muted-2 text-xs font-mono px-2 py-0.5 rounded-pill">
            {total}
          </span>
        </div>

        {/* Filter row */}
        {!isEmpty && (
          <div className="flex flex-wrap items-center gap-2 mt-3">
            {/* Search */}
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-3 pointer-events-none" />
              <input
                type="text"
                placeholder="Поиск..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 pr-3 py-1.5 text-sm bg-canvas border border-black/10 rounded-pill outline-none focus:border-accent/40 focus:bg-white transition-all duration-300 w-40"
              />
            </div>

            <span className="text-muted-3 text-xs">|</span>

            {/* Priority chips */}
            <div className="flex gap-1">
              <button
                onClick={() => setPriorityFilter(null)}
                className={`px-3 py-1 rounded-pill text-xs font-semibold transition-all duration-200 ${
                  priorityFilter === null ? "bg-accent text-white" : "bg-canvas text-muted hover:bg-canvas-2"
                }`}
              >
                Все
              </button>
              {PRIORITIES.map((p) => (
                <button
                  key={p}
                  onClick={() => setPriorityFilter(priorityFilter === p ? null : p)}
                  className={`px-3 py-1 rounded-pill text-xs font-bold transition-all duration-200 ${
                    priorityFilter === p ? "bg-accent text-white" : "bg-canvas text-muted hover:bg-canvas-2"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Body */}
      <div className="max-w-5xl mx-auto px-6 py-6">
        {isLoading && (
          <div className="flex items-center justify-center py-20 text-muted-2 text-sm">
            Загрузка...
          </div>
        )}

        {isError && (
          <div className="flex items-center justify-center py-20 text-rose text-sm">
            Ошибка загрузки данных. Проверьте подключение к API.
          </div>
        )}

        {isEmpty && !isError && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="bg-white border border-black/5 rounded-2xl p-10 shadow-soft max-w-sm w-full">
              <p className="text-lg font-extrabold tracking-tight mb-2">Начните с плана на неделю</p>
              <p className="text-sm text-muted mb-6">
                У вас пока нет лидов в работе. Сформируйте спринт — и они появятся здесь.
              </p>
              <button
                onClick={() => setSprintOpen(true)}
                className="inline-flex items-center gap-2 bg-accent text-white rounded-pill px-5 py-2.5 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-accent/90 active:scale-[0.98]"
              >
                Сформировать план →
              </button>
            </div>
          </div>
        )}

        {!isLoading && !isError && !isEmpty && (
          <>
            <Section title="Сегодня" leads={groups.today} />
            <Section title="Завтра" leads={groups.tomorrow} />
            <Section title="Эта неделя" leads={groups.week} />
            <Section title="Без срока" leads={groups.nodate} />
            {total === 0 && (
              <p className="text-center text-sm text-muted py-10">
                Нет лидов по выбранным фильтрам.
              </p>
            )}
          </>
        )}
      </div>

      {/* Sprint modal — standalone mode */}
      <SprintModal isOpen={sprintOpen} onClose={() => setSprintOpen(false)} />
    </>
  );
}
