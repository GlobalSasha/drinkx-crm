"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { RefreshCw, Sparkles, CheckCircle2, Circle, ArrowRight } from "lucide-react";
import { useTodayPlan, useRegenerate, useCompletePlanItem } from "@/lib/hooks/use-daily-plan";
import { segmentLabel } from "@/lib/i18n";
import { tierFromScore } from "@/lib/types";
import type { DailyPlanItem, TimeBlock, TaskKind } from "@/lib/types";

// ---- Constants ----

const PAGE_SIZE = 10;

// ---- Labels ----

const TIME_BLOCK_LABEL: Record<TimeBlock, string> = {
  morning: "Утро",
  midday: "День",
  afternoon: "После обеда",
  evening: "Вечер",
};

const TASK_KIND_LABEL: Record<TaskKind, string> = {
  call: "Звонок",
  email: "Почта",
  meeting: "Встреча",
  research: "Изучить",
  follow_up: "Follow-up",
};

const TASK_KIND_STYLE: Record<TaskKind, string> = {
  call: "bg-accent/10 text-accent",
  email: "bg-success/10 text-success",
  meeting: "bg-warning/10 text-warning",
  research: "bg-black/5 text-muted",
  follow_up: "bg-rose/10 text-rose",
};

const PRIORITY_STYLE: Record<string, string> = {
  A: "bg-accent/10 text-accent",
  B: "bg-success/10 text-success",
  C: "bg-warning/10 text-warning",
  D: "bg-black/5 text-muted",
};

const TIME_BLOCK_ORDER: (TimeBlock | null)[] = [
  "morning",
  "midday",
  "afternoon",
  "evening",
  null,
];

// ---- Date helpers ----

const TODAY_DATE = new Date().toLocaleDateString("ru-RU", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ---- Sub-components ----

function SkeletonCard() {
  return (
    <div className="animate-pulse flex items-center gap-3 bg-white border border-black/5 rounded-xl px-4 py-3 h-[72px]">
      <div className="w-5 h-5 rounded-full bg-black/5 shrink-0" />
      <div className="w-14 h-4 bg-black/5 rounded shrink-0" />
      <div className="flex-1 space-y-1.5">
        <div className="h-3.5 bg-black/5 rounded w-2/5" />
        <div className="h-2.5 bg-black/5 rounded w-3/4" />
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <div className="w-6 h-4 bg-black/5 rounded" />
        <div className="w-10 h-4 bg-black/5 rounded" />
        <div className="w-10 h-4 bg-black/5 rounded" />
      </div>
    </div>
  );
}

function PlanItemCard({ item, index }: { item: DailyPlanItem; index: number }) {
  const router = useRouter();
  const { mutate: complete, isPending } = useCompletePlanItem();

  const taskKind = item.task_kind as TaskKind;
  const kindLabel = TASK_KIND_LABEL[taskKind] ?? item.task_kind;
  const kindStyle = TASK_KIND_STYLE[taskKind] ?? "bg-black/5 text-muted";
  const tier = tierFromScore(item.priority_score);
  const priorityStyle = PRIORITY_STYLE[tier] ?? "bg-black/5 text-muted";
  const isHot = item.priority_score >= 80;

  // Build segment+city label
  const segCity = [
    item.lead_segment ? segmentLabel(item.lead_segment) : null,
    item.lead_city,
  ]
    .filter(Boolean)
    .join(", ");

  function handleCheck(e: React.MouseEvent) {
    e.stopPropagation();
    if (!item.done && !isPending) {
      complete(item.id);
    }
  }

  function handleOpen(e: React.MouseEvent) {
    e.stopPropagation();
    if (item.lead_id) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      router.push(`/leads/${item.lead_id}` as any);
    }
  }

  return (
    <div
      className={`relative flex flex-col bg-white border border-black/5 rounded-xl shadow-soft transition-all duration-300 overflow-hidden ${
        item.done ? "opacity-50" : ""
      } ${isHot && !item.done ? "border-l-2 border-l-accent" : ""}`}
    >
      {/* Main row */}
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Checkbox */}
        <button
          onClick={handleCheck}
          disabled={item.done || isPending}
          className="shrink-0 text-muted-3 hover:text-success transition-colors disabled:cursor-default"
          aria-label={item.done ? "Выполнено" : "Отметить выполненным"}
        >
          {item.done ? (
            <CheckCircle2 size={18} className="text-success" />
          ) : (
            <Circle size={18} />
          )}
        </button>

        {/* Position · task_kind pill */}
        <span
          className={`shrink-0 font-mono text-[10px] font-semibold px-2 py-0.5 rounded-md whitespace-nowrap ${kindStyle}`}
        >
          {String(index).padStart(2, "0")} · {kindLabel}
        </span>

        {/* Company + segment/city — takes remaining space */}
        <div className="flex-1 min-w-0">
          <button
            onClick={handleOpen}
            disabled={!item.lead_id}
            className={`font-semibold text-sm text-ink leading-snug truncate block max-w-full text-left ${
              item.done ? "line-through" : ""
            } ${item.lead_id ? "hover:text-accent transition-colors" : "cursor-default"}`}
          >
            {item.lead_company_name ?? "—"}
          </button>
          {segCity && (
            <p className="font-mono text-[10px] text-muted-3 truncate leading-tight mt-0.5 lowercase">
              {segCity}
            </p>
          )}
        </div>

        {/* Right-edge cluster */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Priority tier chip */}
          <span
            className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded-md ${priorityStyle}`}
          >
            {tier}
          </span>

          {/* Score */}
          <span className="font-mono text-[10px] text-muted-2 tabular-nums">
            {Math.round(item.priority_score)}
          </span>

          {/* Estimated minutes */}
          <span className="font-mono text-[10px] text-muted-3 tabular-nums whitespace-nowrap">
            {item.estimated_minutes} мин
          </span>

          {/* Открыть link */}
          {item.lead_id && (
            <button
              onClick={handleOpen}
              className="inline-flex items-center gap-0.5 text-[11px] font-semibold text-accent hover:text-accent/70 transition-colors"
              aria-label={`Открыть ${item.lead_company_name}`}
            >
              Открыть
              <ArrowRight size={11} />
            </button>
          )}
        </div>
      </div>

      {/* Hint line */}
      {item.hint_one_liner && (
        <p
          className={`px-4 pb-2.5 text-[11px] text-muted-2 leading-tight truncate -mt-1 ${
            item.done ? "line-through" : ""
          }`}
          title={item.hint_one_liner}
        >
          {item.hint_one_liner}
        </p>
      )}
    </div>
  );
}

function TimeBlockSection({
  block,
  items,
  doneCount,
}: {
  block: TimeBlock | null;
  items: DailyPlanItem[];
  doneCount: number;
}) {
  if (items.length === 0) return null;

  const label = block ? TIME_BLOCK_LABEL[block] : "Без времени";

  return (
    <div className="mb-6">
      {/* Heading */}
      <div className="flex items-center gap-2 mb-2">
        <span className="font-mono uppercase tracking-[0.2em] text-[10px] text-muted-2">
          {label}
        </span>
        <span className="bg-black/5 text-muted-2 font-mono text-[10px] px-2 py-0.5 rounded-pill tabular-nums">
          {items.length}
          {doneCount > 0 && (
            <> · {doneCount} ✓</>
          )}
        </span>
      </div>
      <div className="border-t border-black/5 mb-3" />
      {/* Cards */}
      <div className="flex flex-col gap-2">
        {items.map((item, i) => (
          <PlanItemCard key={item.id} item={item} index={item.position} />
        ))}
      </div>
    </div>
  );
}

// ---- Pagination controls ----

function Pagination({
  currentPage,
  totalPages,
  onPage,
}: {
  currentPage: number;
  totalPages: number;
  onPage: (p: number) => void;
}) {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-1 mt-8 mb-2">
      {/* Prev arrow */}
      <button
        onClick={() => onPage(currentPage - 1)}
        disabled={currentPage === 1}
        className="w-11 h-11 sm:w-8 sm:h-8 flex items-center justify-center rounded-lg text-muted hover:bg-canvas-2 hover:text-ink transition-colors disabled:opacity-30 disabled:cursor-not-allowed font-mono text-sm"
        aria-label="Предыдущая страница"
      >
        ←
      </button>

      {/* Page numbers */}
      {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
        <button
          key={p}
          onClick={() => onPage(p)}
          className={`w-11 h-11 sm:w-8 sm:h-8 flex items-center justify-center rounded-lg font-mono text-[11px] transition-colors ${
            p === currentPage
              ? "bg-accent text-white font-semibold"
              : "text-muted hover:bg-canvas-2 hover:text-ink"
          }`}
          aria-label={`Страница ${p}`}
          aria-current={p === currentPage ? "page" : undefined}
        >
          {p}
        </button>
      ))}

      {/* Next arrow */}
      <button
        onClick={() => onPage(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="w-11 h-11 sm:w-8 sm:h-8 flex items-center justify-center rounded-lg text-muted hover:bg-canvas-2 hover:text-ink transition-colors disabled:opacity-30 disabled:cursor-not-allowed font-mono text-sm"
        aria-label="Следующая страница"
      >
        →
      </button>
    </div>
  );
}

// ---- Inner page (uses useSearchParams — must be inside Suspense) ----

function TodayPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { data: plan, isLoading, isError } = useTodayPlan();
  const { mutate: regenerate, isPending: isRegenerating } = useRegenerate();

  // Derive page from URL, default 1
  const pageParam = parseInt(searchParams.get("page") ?? "1", 10);
  const [page, setPage] = useState(isNaN(pageParam) || pageParam < 1 ? 1 : pageParam);

  // Reset to page 1 when plan regenerates (status changes to generating then ready)
  const planId = plan?.id;
  useEffect(() => {
    setPage(1);
    const url = new URL(window.location.href);
    url.searchParams.delete("page");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    router.replace((url.pathname + (url.search === "?" ? "" : url.search)) as any, { scroll: false });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId]);

  const totalItems = plan?.summary_json?.count ?? plan?.items?.length ?? 0;
  const totalMinutes = plan?.summary_json?.total_minutes ?? 0;

  function handleRegenerate() {
    regenerate(todayIso());
  }

  function goToPage(p: number) {
    const url = new URL(window.location.href);
    if (p === 1) {
      url.searchParams.delete("page");
    } else {
      url.searchParams.set("page", String(p));
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    router.push((url.pathname + url.search) as any, { scroll: false });
    setPage(p);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---- Pagination logic ----
  // Sort all items by position, slice for current page
  const allItems = plan?.items ?? [];
  const sortedItems = [...allItems].sort((a, b) => a.position - b.position);
  const totalPages = Math.ceil(sortedItems.length / PAGE_SIZE);
  const safePage = Math.min(Math.max(page, 1), Math.max(totalPages, 1));
  const pageItems = sortedItems.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // Group page items by time_block, preserving order
  const groupedItems: Map<TimeBlock | null, DailyPlanItem[]> = new Map();
  for (const block of TIME_BLOCK_ORDER) {
    const matching = pageItems.filter((i) => (i.time_block ?? null) === block);
    if (matching.length > 0) {
      groupedItems.set(block, matching);
    }
  }

  // Done counts per block (from full plan, not page slice — for heading badge accuracy)
  function doneCountForBlock(block: TimeBlock | null): number {
    return allItems.filter(
      (i) => (i.time_block ?? null) === block && i.done
    ).length;
  }

  const isGenerating = plan?.status === "generating" || isRegenerating;

  return (
    <>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white/95 backdrop-blur-sm border-b border-black/5 px-4 sm:px-6 py-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3 max-w-4xl mx-auto">
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-xl font-extrabold tracking-tight">Сегодня</h1>
              <span className="font-mono text-[11px] text-muted-2 lowercase">{TODAY_DATE}</span>
            </div>
            {plan?.status === "ready" && (
              <p className="font-mono text-[10px] text-muted-3 mt-0.5 tabular-nums">
                {totalItems} задач
                {totalMinutes > 0 && ` · ${totalMinutes} мин`}
                {totalPages > 1 && ` · стр. ${safePage} из ${totalPages}`}
              </p>
            )}
          </div>

          {/* Regenerate button */}
          <button
            onClick={handleRegenerate}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 bg-canvas border border-black/10 text-muted text-xs font-semibold rounded-pill px-4 py-2 hover:bg-canvas-2 hover:text-ink transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            <RefreshCw size={13} className={isGenerating ? "animate-spin" : ""} />
            <span className="hidden sm:inline">Пересобрать план</span>
            <span className="sm:hidden">Пересобрать</span>
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">

        {/* Loading initial */}
        {isLoading && (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* API error */}
        {isError && (
          <div className="flex items-center justify-center py-20 text-rose text-sm">
            Ошибка загрузки плана. Проверьте подключение к API.
          </div>
        )}

        {/* No plan yet — empty state */}
        {!isLoading && !isError && !plan && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="bg-white border border-black/5 rounded-2xl p-10 shadow-soft max-w-md w-full mx-auto">
              <Sparkles size={32} className="mx-auto mb-4 text-muted-3" />
              <p className="text-lg font-extrabold tracking-tight mb-2">
                План на сегодня ещё не сформирован
              </p>
              <p className="text-sm text-muted mb-6">
                Нажмите «Сформировать», чтобы AI собрал список задач на основе
                ваших активных лидов.
              </p>
              <button
                onClick={handleRegenerate}
                disabled={isRegenerating}
                className="inline-flex items-center gap-2 bg-accent text-white rounded-pill px-5 py-2.5 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-accent/90 active:scale-[0.98] disabled:opacity-60"
              >
                {isRegenerating ? (
                  <RefreshCw size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} />
                )}
                Сформировать
              </button>
            </div>
          </div>
        )}

        {/* Generating state */}
        {!isLoading && !isError && plan?.status === "generating" && (
          <div className="flex flex-col gap-2">
            <p className="text-[11px] text-muted-2 mb-2 font-mono text-center tracking-wide uppercase">
              AI собирает план…
            </p>
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Failed state */}
        {!isLoading && !isError && plan?.status === "failed" && (
          <div className="bg-rose/5 border border-rose/20 rounded-2xl p-6 mb-6">
            <p className="text-sm font-semibold text-rose mb-1">Ошибка генерации</p>
            <p className="text-xs text-rose/80 font-mono mb-4 line-clamp-2">
              {plan.generation_error ?? "Неизвестная ошибка"}
            </p>
            <button
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="inline-flex items-center gap-2 bg-rose text-white rounded-pill px-4 py-2 text-xs font-semibold hover:bg-rose/90 transition-colors disabled:opacity-60"
            >
              <RefreshCw size={12} className={isRegenerating ? "animate-spin" : ""} />
              Попробовать снова
            </button>
          </div>
        )}

        {/* Ready state — paginated time-blocked sections */}
        {!isLoading && !isError && plan?.status === "ready" && (
          <>
            {groupedItems.size === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="bg-white border border-black/5 rounded-2xl p-10 shadow-soft max-w-md w-full mx-auto">
                  <Sparkles size={32} className="mx-auto mb-4 text-muted-3" />
                  <p className="text-base font-semibold text-ink mb-2">План пуст</p>
                  <p className="text-sm text-muted">
                    В вашем плане нет задач на сегодня.
                  </p>
                </div>
              </div>
            ) : (
              <>
                {Array.from(groupedItems.entries()).map(([block, items]) => (
                  <TimeBlockSection
                    key={block ?? "null"}
                    block={block}
                    items={items}
                    doneCount={doneCountForBlock(block)}
                  />
                ))}
                <Pagination
                  currentPage={safePage}
                  totalPages={totalPages}
                  onPage={goToPage}
                />
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}

// ---- Page (Suspense boundary for useSearchParams in Next 15) ----

export default function TodayPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-4xl mx-auto px-6 py-6 flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      }
    >
      <TodayPageInner />
    </Suspense>
  );
}
