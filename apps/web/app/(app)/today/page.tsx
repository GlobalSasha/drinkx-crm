"use client";

import { useRouter } from "next/navigation";
import { RefreshCw, Sparkles, CheckCircle2, Circle } from "lucide-react";
import { useTodayPlan, useRegenerate, useCompletePlanItem } from "@/lib/hooks/use-daily-plan";
import type { DailyPlanItem, TimeBlock, TaskKind } from "@/lib/types";

// ---- Labels ----

const TIME_BLOCK_LABEL: Record<TimeBlock, string> = {
  morning: "Утро",
  midday: "День",
  afternoon: "После обеда",
  evening: "Вечер",
};

const TASK_KIND_LABEL: Record<TaskKind, string> = {
  call: "Звонок",
  email: "Email",
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

function SkeletonItem() {
  return (
    <div className="animate-pulse flex items-start gap-4 bg-white border border-black/5 rounded-2xl p-5">
      <div className="w-5 h-5 rounded-full bg-black/5 shrink-0 mt-0.5" />
      <div className="flex-1 space-y-2">
        <div className="h-4 bg-black/5 rounded w-2/5" />
        <div className="h-3 bg-black/5 rounded w-1/3" />
        <div className="h-3 bg-black/5 rounded w-3/4" />
      </div>
    </div>
  );
}

function PlanItemCard({ item }: { item: DailyPlanItem }) {
  const router = useRouter();
  const { mutate: complete, isPending } = useCompletePlanItem();

  const taskKind = item.task_kind as TaskKind;
  const kindLabel = TASK_KIND_LABEL[taskKind] ?? item.task_kind;
  const kindStyle = TASK_KIND_STYLE[taskKind] ?? "bg-black/5 text-muted";

  function handleCheck(e: React.MouseEvent) {
    e.stopPropagation();
    if (!item.done && !isPending) {
      complete(item.id);
    }
  }

  function handleCardClick() {
    if (item.lead_id) {
      router.push(`/leads/${item.lead_id}`);
    }
  }

  return (
    <div
      onClick={handleCardClick}
      className={`flex items-start gap-4 bg-white border border-black/5 rounded-2xl shadow-soft p-5 transition-all duration-300 ${
        item.lead_id ? "cursor-pointer hover:shadow-md hover:-translate-y-0.5" : ""
      } ${item.done ? "opacity-50" : ""}`}
    >
      {/* Checkbox */}
      <button
        onClick={handleCheck}
        disabled={item.done || isPending}
        className="shrink-0 mt-0.5 text-muted-3 hover:text-success transition-colors disabled:cursor-default"
        aria-label={item.done ? "Выполнено" : "Отметить выполненным"}
      >
        {item.done ? (
          <CheckCircle2 size={20} className="text-success" />
        ) : (
          <Circle size={20} />
        )}
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Company + meta */}
        <div className="flex items-start justify-between gap-2">
          <p className={`font-semibold text-sm text-ink leading-snug ${item.done ? "line-through" : ""}`}>
            {item.lead_company_name ?? "—"}
          </p>
          <div className="flex items-center gap-1.5 shrink-0">
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-pill ${kindStyle}`}>
              {kindLabel}
            </span>
          </div>
        </div>

        {/* Segment + city */}
        {(item.lead_segment || item.lead_city) && (
          <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-2 mt-0.5 truncate">
            {[item.lead_segment, item.lead_city].filter(Boolean).join(" · ")}
          </p>
        )}

        {/* Hint */}
        <p className="text-sm text-muted mt-1.5 leading-snug line-clamp-1">
          {item.hint_one_liner}
        </p>

        {/* Footer: minutes + score */}
        <div className="flex items-center gap-3 mt-2">
          <span className="font-mono text-[10px] text-muted-3">
            {item.estimated_minutes} мин
          </span>
          <span className="font-mono text-[10px] text-muted-3">
            {Number(item.priority_score).toFixed(1)}
          </span>
        </div>
      </div>
    </div>
  );
}

function TimeBlockSection({
  block,
  items,
}: {
  block: TimeBlock | null;
  items: DailyPlanItem[];
}) {
  if (items.length === 0) return null;

  const label = block ? TIME_BLOCK_LABEL[block] : "Без времени";

  return (
    <div className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <span className="font-mono uppercase tracking-[0.2em] text-[10px] text-muted-2">
          {label}
        </span>
        <span className="bg-black/5 text-muted-2 font-mono text-[10px] px-1.5 py-0.5 rounded-pill">
          {items.length}
        </span>
      </div>
      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <PlanItemCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}

// ---- Page ----

export default function TodayPage() {
  const { data: plan, isLoading, isError } = useTodayPlan();
  const { mutate: regenerate, isPending: isRegenerating } = useRegenerate();

  const totalItems = plan?.summary_json?.count ?? plan?.items?.length ?? 0;
  const totalMinutes = plan?.summary_json?.total_minutes ?? 0;

  function handleRegenerate() {
    regenerate(todayIso());
  }

  // Group items by time_block preserving order
  const groupedItems: Map<TimeBlock | null, DailyPlanItem[]> = new Map();
  if (plan?.items) {
    for (const block of TIME_BLOCK_ORDER) {
      const matching = plan.items.filter((i) => (i.time_block ?? null) === block);
      if (matching.length > 0) {
        groupedItems.set(block, matching);
      }
    }
  }

  const isGenerating = plan?.status === "generating" || isRegenerating;

  return (
    <>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b border-black/5 px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-extrabold tracking-tight">Сегодня</h1>
            <span className="font-mono text-[11px] text-muted-2 lowercase">{TODAY_DATE}</span>
            {plan?.status === "ready" && (
              <>
                <span className="bg-black/5 text-muted-2 text-xs font-mono px-2 py-0.5 rounded-pill">
                  {totalItems} задач
                </span>
                {totalMinutes > 0 && (
                  <span className="bg-black/5 text-muted-2 text-xs font-mono px-2 py-0.5 rounded-pill">
                    {totalMinutes} мин
                  </span>
                )}
              </>
            )}
          </div>

          {/* Regenerate button */}
          <button
            onClick={handleRegenerate}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 bg-canvas border border-black/10 text-muted text-xs font-semibold rounded-pill px-4 py-2 hover:bg-canvas-2 hover:text-ink transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw size={13} className={isGenerating ? "animate-spin" : ""} />
            Пересобрать план
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="max-w-4xl mx-auto px-6 py-6">

        {/* Loading initial */}
        {isLoading && (
          <div className="flex flex-col gap-3">
            <SkeletonItem />
            <SkeletonItem />
            <SkeletonItem />
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
            <div className="bg-white border border-black/5 rounded-2xl p-10 shadow-soft max-w-sm w-full">
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
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-2 mb-1 text-center">
              AI собирает план…
            </p>
            <SkeletonItem />
            <SkeletonItem />
            <SkeletonItem />
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

        {/* Ready state — time-blocked sections */}
        {!isLoading && !isError && plan?.status === "ready" && (
          <>
            {groupedItems.size === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="bg-white border border-black/5 rounded-2xl p-10 shadow-soft max-w-sm w-full">
                  <Sparkles size={32} className="mx-auto mb-4 text-muted-3" />
                  <p className="text-base font-semibold text-ink mb-2">План пуст</p>
                  <p className="text-sm text-muted">
                    В вашем плане нет задач на сегодня.
                  </p>
                </div>
              </div>
            ) : (
              Array.from(groupedItems.entries()).map(([block, items]) => (
                <TimeBlockSection key={block ?? "null"} block={block} items={items} />
              ))
            )}
          </>
        )}
      </div>
    </>
  );
}
