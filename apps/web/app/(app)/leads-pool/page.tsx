"use client";
import { useState, useMemo, useCallback } from "react";
import { Search, Loader2 } from "lucide-react";
import { usePoolLeads, useClaimLead } from "@/lib/hooks/use-leads";
import { Toast } from "@/components/ui/Toast";
import { ExportPopover } from "@/components/export/ExportPopover";
import { tierFromScore } from "@/lib/types";
import type { LeadOut } from "@/lib/types";

// Russian-friendly labels for backend segment slugs (matches build_data.py).
// Unknown slugs fall back to the raw string so we don't lose data.
const SEGMENT_LABELS: Record<string, string> = {
  food_retail: "Продуктовый ритейл",
  non_food_retail: "Непродуктовый ритейл",
  coffee_shops: "Кофейни и кафе",
  qsr_fast_food: "QSR / Fast Food",
  gas_stations: "АЗС",
  coffee_equipment_distributors: "Дистрибьюторы оборудования",
  horeca: "HoReCa",
  restaurants: "Рестораны",
  hotels: "Отели",
};

const segmentLabel = (s: string) => SEGMENT_LABELS[s] ?? s;

// ---- Toast state ----

interface ToastState {
  id: number;
  message: string;
  type: "error" | "success";
}

// ---- Fit score slider ----

function FitSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-2 whitespace-nowrap">
        Fit ≥ {value}
      </span>
      <input
        type="range"
        min={0}
        max={10}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-24 accent-accent"
      />
    </div>
  );
}

// ---- Row component ----

function PoolRow({
  lead,
  onClaim,
  claiming,
}: {
  lead: LeadOut;
  onClaim: (id: string) => void;
  claiming: boolean;
}) {
  const tier = tierFromScore(lead.score);
  const TIER_STYLE: Record<string, string> = {
    A: "bg-accent/10 text-accent",
    B: "bg-success/10 text-success",
    C: "bg-warning/10 text-warning",
    D: "bg-black/5 text-muted",
  };

  return (
    <tr
      className={`border-b border-black/5 transition-opacity duration-300 ${claiming ? "opacity-40" : "hover:bg-canvas"}`}
    >
      <td className="px-4 py-3">
        <p className="font-semibold text-sm text-ink">{lead.company_name}</p>
      </td>
      <td className="px-4 py-3 text-sm text-muted-2">{lead.city ?? "—"}</td>
      <td className="px-4 py-3 text-sm text-muted-2">{lead.segment ? segmentLabel(lead.segment) : "—"}</td>
      <td className="px-4 py-3">
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md ${TIER_STYLE[tier]}`}>
          {tier}
        </span>
      </td>
      <td className="px-4 py-3 font-mono text-sm text-muted-2">
        {lead.fit_score != null ? lead.fit_score : "—"}
      </td>
      <td className="px-4 py-3">
        <span className="text-[10px] font-mono bg-black/5 text-muted px-1.5 py-0.5 rounded-md">
          {lead.assignment_status}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        {claiming ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-2 font-semibold">
            <Loader2 size={12} className="animate-spin" /> Взято
          </span>
        ) : (
          <button
            onClick={() => onClaim(lead.id)}
            className="inline-flex items-center gap-1.5 bg-accent text-white rounded-pill px-3 py-1.5 text-xs font-semibold transition-all duration-200 hover:bg-accent/90 active:scale-[0.98]"
          >
            Взять в работу
          </button>
        )}
      </td>
    </tr>
  );
}

// ---- Page ----

export default function LeadsPoolPage() {
  const [cityFilter, setCityFilter] = useState<string | null>(null);
  const [segmentFilter, setSegmentFilter] = useState<string | null>(null);
  const [fitMin, setFitMin] = useState(0);
  const [search, setSearch] = useState("");
  const [toasts, setToasts] = useState<ToastState[]>([]);
  // Track which lead IDs are currently being claimed (for optimistic UI)
  const [claimingIds, setClaimingIds] = useState<Set<string>>(new Set());

  const addToast = useCallback((message: string, type: "error" | "success" = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  // Fetch the WHOLE pool once and filter client-side. Per-chip counts only
  // make sense against the unfiltered pool — passing city/segment to the
  // backend means each chip would just show the size of the active filter
  // (or zero for non-active ones). 216 leads ≈ 50KB, fine for one fetch;
  // revisit if pool grows past a few thousand.
  const poolQuery = usePoolLeads({ page_size: 500 });
  const claimMutation = useClaimLead();

  const allItems = poolQuery.data?.items ?? [];

  // Sorted unique values for the chip rows
  const cities = useMemo(
    () => Array.from(new Set(allItems.map((l) => l.city).filter(Boolean) as string[])).sort(),
    [allItems]
  );
  const segments = useMemo(
    () => Array.from(new Set(allItems.map((l) => l.segment).filter(Boolean) as string[])).sort(),
    [allItems]
  );

  // Per-segment / per-city counts on the unfiltered pool — populates the
  // count badges inside chips so a manager sees "Кофейни и кафе · 29"
  // before clicking.
  const segmentCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of allItems) {
      if (!l.segment) continue;
      m.set(l.segment, (m.get(l.segment) ?? 0) + 1);
    }
    return m;
  }, [allItems]);
  const cityCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of allItems) {
      if (!l.city) continue;
      m.set(l.city, (m.get(l.city) ?? 0) + 1);
    }
    return m;
  }, [allItems]);

  // Apply ALL filters client-side: city + segment + fit_min + search
  const filtered = useMemo(() => {
    return allItems.filter((l) => {
      if (cityFilter && l.city !== cityFilter) return false;
      if (segmentFilter && l.segment !== segmentFilter) return false;
      if (fitMin > 0 && (l.fit_score == null || l.fit_score < fitMin)) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!l.company_name.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [allItems, cityFilter, segmentFilter, fitMin, search]);

  function handleClaim(id: string) {
    // Optimistic: gray row immediately
    setClaimingIds((prev) => new Set(prev).add(id));

    claimMutation.mutate(id, {
      onSuccess: () => {
        setClaimingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        addToast("Лид взят в работу", "success");
      },
      onError: (err) => {
        setClaimingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        const message =
          err.status === 409
            ? "Эту карточку только что взял другой менеджер"
            : "Ошибка при взятии лида";
        addToast(message, "error");
      },
    });
  }

  const isLoading = poolQuery.isLoading;
  const isError = poolQuery.isError;

  return (
    <>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b border-black/5 px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-baseline gap-2">
            <h1 className="text-xl font-extrabold tracking-tight">База лидов</h1>
            {/* Compact total — shown small next to title, the loud counts
                live inside each chip below. */}
            <span className="text-muted-3 text-xs font-mono tabular-nums">
              {filtered.length}
              {filtered.length !== allItems.length && (
                <span className="text-muted-3"> / {allItems.length}</span>
              )}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <ExportPopover
              filters={{
                city: cityFilter ?? undefined,
                segment: segmentFilter ?? undefined,
                fit_min: fitMin > 0 ? fitMin : undefined,
                q: search || undefined,
                assignment_status: "pool",
              }}
              leadCount={filtered.length}
            />
            {/* "Только мой пул" placeholder toggle */}
            <label className="flex items-center gap-2 cursor-pointer opacity-50" title="Скоро">
              <span className="text-xs font-semibold text-muted">Только мой пул</span>
              <div className="w-8 h-4 rounded-pill bg-black/10" />
            </label>
          </div>
        </div>

        {/* Filter row */}
        <div className="flex flex-wrap items-center gap-3 mt-3">
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

          {/* City chips */}
          {cities.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <ChipButton
                active={cityFilter === null}
                onClick={() => setCityFilter(null)}
                count={allItems.length}
              >
                Все города
              </ChipButton>
              {cities.map((c) => (
                <ChipButton
                  key={c}
                  active={cityFilter === c}
                  onClick={() => setCityFilter(cityFilter === c ? null : c)}
                  count={cityCounts.get(c) ?? 0}
                >
                  {c}
                </ChipButton>
              ))}
            </div>
          )}

          {segments.length > 0 && (
            <>
              <span className="text-muted-3 text-xs">|</span>
              {/* Segment chips with Russian labels + per-segment counts */}
              <div className="flex flex-wrap gap-1">
                <ChipButton
                  active={segmentFilter === null}
                  onClick={() => setSegmentFilter(null)}
                  count={allItems.length}
                >
                  Все сегменты
                </ChipButton>
                {segments.map((s) => (
                  <ChipButton
                    key={s}
                    active={segmentFilter === s}
                    onClick={() => setSegmentFilter(segmentFilter === s ? null : s)}
                    count={segmentCounts.get(s) ?? 0}
                  >
                    {segmentLabel(s)}
                  </ChipButton>
                ))}
              </div>
            </>
          )}

          <span className="text-muted-3 text-xs">|</span>

          <FitSlider value={fitMin} onChange={setFitMin} />
        </div>
      </div>

      {/* Body */}
      <div className="px-6 py-6">
        {isLoading && (
          <div className="flex items-center justify-center py-20 gap-2 text-muted-2 text-sm">
            <Loader2 size={18} className="animate-spin" /> Загрузка...
          </div>
        )}

        {isError && (
          <div className="flex items-center justify-center py-20 text-rose text-sm">
            Ошибка загрузки данных. Проверьте подключение к API.
          </div>
        )}

        {!isLoading && !isError && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="bg-white border border-black/5 rounded-2xl p-10 shadow-soft max-w-sm w-full">
              <p className="text-lg font-extrabold tracking-tight mb-2">В пуле пока пусто</p>
              <p className="text-sm text-muted">
                Импортируйте леды или добавьте вручную.
              </p>
            </div>
          </div>
        )}

        {!isLoading && !isError && filtered.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-black/5 bg-white">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-black/5">
                  {["Компания", "Город", "Сегмент", "Tier", "Fit Score", "Статус", ""].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-2 whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((lead) => (
                  <PoolRow
                    key={lead.id}
                    lead={lead}
                    onClaim={handleClaim}
                    claiming={claimingIds.has(lead.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Toast stack */}
      <div className="fixed bottom-6 right-6 flex flex-col gap-2 z-50 pointer-events-none">
        {toasts.map((t) => (
          <Toast key={t.id} message={t.message} type={t.type} />
        ))}
      </div>
    </>
  );
}

function ChipButton({
  active,
  onClick,
  count,
  children,
}: {
  active: boolean;
  onClick: () => void;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 pl-3 pr-2.5 py-1 rounded-pill text-xs font-semibold transition-all duration-200 ${
        active
          ? "bg-accent text-white"
          : "bg-canvas text-muted hover:bg-canvas-2"
      }`}
    >
      <span>{children}</span>
      {count != null && (
        <span
          className={`tabular-nums text-[10px] leading-none font-mono px-1.5 py-0.5 rounded-pill ${
            active ? "bg-white/15 text-white" : "bg-black/5 text-muted-2"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}
