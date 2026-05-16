"use client";
import { useState, useMemo, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2, Sparkles, X } from "lucide-react";
import { usePoolLeads, useClaimLead } from "@/lib/hooks/use-leads";
import { Toast } from "@/components/ui/Toast";
import { ExportPopover } from "@/components/export/ExportPopover";
import { AIBulkUpdateModal } from "@/components/export/AIBulkUpdateModal";
import { T } from "@/lib/design-system";
import { tierFromScore } from "@/lib/types";
import type { LeadOut } from "@/lib/types";
import { segmentLabel, SEGMENT_OPTIONS } from "@/lib/i18n";
import { MultiSelectDropdown } from "@/components/ui/MultiSelectDropdown";

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
      <span className={`${T.mono} uppercase text-muted-2 whitespace-nowrap`}>
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
  const router = useRouter();
  const tier = tierFromScore(lead.score);
  const TIER_STYLE: Record<string, string> = {
    A: "bg-brand-soft text-brand-accent",
    B: "bg-success/10 text-success",
    C: "bg-warning/10 text-warning",
    D: "bg-black/5 text-muted",
  };

  function openLead() {
    router.push(`/leads/${lead.id}`);
  }

  function handleClaim(e: React.MouseEvent) {
    // Stop propagation so the row click doesn't fire after the button click.
    e.stopPropagation();
    onClaim(lead.id);
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      openLead();
    }
  }

  return (
    <tr
      role="link"
      tabIndex={0}
      aria-label={`Открыть лид ${lead.company_name}`}
      onClick={openLead}
      onKeyDown={handleKey}
      className={`border-b border-black/5 transition-opacity duration-300 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-inset ${claiming ? "opacity-40" : "hover:bg-canvas"}`}
    >
      <td className="px-4 py-3">
        <p className="font-semibold text-sm text-ink">{lead.company_name}</p>
      </td>
      <td className="px-4 py-3 text-sm text-muted-2">{lead.city ?? "—"}</td>
      <td className="px-4 py-3 text-sm text-muted-2">{lead.segment ? segmentLabel(lead.segment) : "—"}</td>
      <td className="px-4 py-3">
        <span className={`text-xs font-bold px-1.5 py-0.5 rounded-md ${TIER_STYLE[tier]}`}>
          {tier}
        </span>
      </td>
      <td className="px-4 py-3 type-amount text-muted-2">
        {lead.fit_score != null ? lead.fit_score : "—"}
      </td>
      <td className="px-4 py-3">
        <span className={`${T.mono} bg-black/5 text-muted px-1.5 py-0.5 rounded-md`}>
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
            onClick={handleClaim}
            className="inline-flex items-center gap-1.5 bg-brand-accent text-white rounded-pill px-3 py-1.5 text-xs font-semibold transition-all duration-200 hover:bg-brand-accent/90 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            Взять в работу
          </button>
        )}
      </td>
    </tr>
  );
}

// ---- Page ----

const TIER_OPTIONS = ["A", "B", "C", "D"];
const PRIORITY_OPTIONS = ["A", "B", "C", "D"];

export default function LeadsPoolPage() {
  const [cityFilters, setCityFilters] = useState<string[]>([]);
  const [segmentFilters, setSegmentFilters] = useState<string[]>([]);
  const [priorityFilters, setPriorityFilters] = useState<string[]>([]);
  const [tierFilters, setTierFilters] = useState<string[]>([]);
  const [dealTypeFilters, setDealTypeFilters] = useState<string[]>([]);
  const [sourceFilters, setSourceFilters] = useState<string[]>([]);
  const [tagFilters, setTagFilters] = useState<string[]>([]);
  const [fitMin, setFitMin] = useState(0);
  const [search, setSearch] = useState("");
  const [hasEmailOnly, setHasEmailOnly] = useState(false);
  const [hasPhoneOnly, setHasPhoneOnly] = useState(false);
  const [toasts, setToasts] = useState<ToastState[]>([]);
  // Track which lead IDs are currently being claimed (for optimistic UI)
  const [claimingIds, setClaimingIds] = useState<Set<string>>(new Set());
  const [aiUpdateOpen, setAiUpdateOpen] = useState(false);

  const activeFilterCount =
    (cityFilters.length > 0 ? 1 : 0) +
    (segmentFilters.length > 0 ? 1 : 0) +
    (priorityFilters.length > 0 ? 1 : 0) +
    (tierFilters.length > 0 ? 1 : 0) +
    (dealTypeFilters.length > 0 ? 1 : 0) +
    (sourceFilters.length > 0 ? 1 : 0) +
    (tagFilters.length > 0 ? 1 : 0) +
    (fitMin > 0 ? 1 : 0) +
    (search ? 1 : 0) +
    (hasEmailOnly ? 1 : 0) +
    (hasPhoneOnly ? 1 : 0);

  function resetAllFilters() {
    setCityFilters([]);
    setSegmentFilters([]);
    setPriorityFilters([]);
    setTierFilters([]);
    setDealTypeFilters([]);
    setSourceFilters([]);
    setTagFilters([]);
    setFitMin(0);
    setSearch("");
    setHasEmailOnly(false);
    setHasPhoneOnly(false);
  }

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

  // Sorted unique values for the filter dropdowns. Segment list = canonical
  // Russian set + any unexpected legacy values still in the pool.
  const cities = useMemo(
    () =>
      Array.from(new Set(allItems.map((l) => l.city).filter(Boolean) as string[])).sort(
        (a, b) => a.localeCompare(b, "ru"),
      ),
    [allItems],
  );
  const segments = useMemo(() => {
    const extras = new Set<string>();
    for (const l of allItems) {
      if (
        l.segment &&
        !SEGMENT_OPTIONS.includes(l.segment as typeof SEGMENT_OPTIONS[number])
      ) {
        extras.add(l.segment);
      }
    }
    return [...SEGMENT_OPTIONS, ...Array.from(extras).sort()];
  }, [allItems]);

  // Per-* counts on the unfiltered pool — shown inside each dropdown
  // row so a manager sees "Кофейни и кафе · 29" before selecting.
  const segmentCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of allItems) {
      if (l.segment) m[l.segment] = (m[l.segment] ?? 0) + 1;
    }
    return m;
  }, [allItems]);
  const cityCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of allItems) {
      if (l.city) m[l.city] = (m[l.city] ?? 0) + 1;
    }
    return m;
  }, [allItems]);
  const priorityCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of allItems) {
      if (l.priority) m[l.priority] = (m[l.priority] ?? 0) + 1;
    }
    return m;
  }, [allItems]);
  const tierCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of allItems) {
      const t = tierFromScore(l.score);
      m[t] = (m[t] ?? 0) + 1;
    }
    return m;
  }, [allItems]);
  const dealTypes = useMemo(
    () =>
      Array.from(
        new Set(allItems.map((l) => l.deal_type).filter(Boolean) as string[]),
      ).sort(),
    [allItems],
  );
  const dealTypeCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of allItems) {
      if (l.deal_type) m[l.deal_type] = (m[l.deal_type] ?? 0) + 1;
    }
    return m;
  }, [allItems]);
  const sources = useMemo(
    () =>
      Array.from(
        new Set(allItems.map((l) => l.source).filter(Boolean) as string[]),
      ).sort(),
    [allItems],
  );
  const sourceCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of allItems) {
      if (l.source) m[l.source] = (m[l.source] ?? 0) + 1;
    }
    return m;
  }, [allItems]);
  const tags = useMemo(() => {
    const set = new Set<string>();
    for (const l of allItems) {
      for (const t of l.tags_json ?? []) set.add(t);
    }
    return Array.from(set).sort();
  }, [allItems]);
  const tagCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of allItems) {
      for (const t of l.tags_json ?? []) m[t] = (m[t] ?? 0) + 1;
    }
    return m;
  }, [allItems]);

  // Apply ALL filters client-side.
  const filtered = useMemo(() => {
    const segSet = new Set(segmentFilters);
    const citySet = new Set(cityFilters);
    const prioSet = new Set(priorityFilters);
    const tierSet = new Set(tierFilters);
    const dealSet = new Set(dealTypeFilters);
    const sourceSet = new Set(sourceFilters);
    const tagSet = new Set(tagFilters);
    const q = search.trim().toLowerCase();
    return allItems.filter((l) => {
      if (citySet.size > 0 && (!l.city || !citySet.has(l.city))) return false;
      if (segSet.size > 0 && (!l.segment || !segSet.has(l.segment))) return false;
      if (prioSet.size > 0 && (!l.priority || !prioSet.has(l.priority))) return false;
      if (tierSet.size > 0 && !tierSet.has(tierFromScore(l.score))) return false;
      if (dealSet.size > 0 && (!l.deal_type || !dealSet.has(l.deal_type))) return false;
      if (sourceSet.size > 0 && (!l.source || !sourceSet.has(l.source))) return false;
      if (tagSet.size > 0) {
        const leadTags = l.tags_json ?? [];
        // AND-match across selected tags — lead must carry every one
        let ok = true;
        for (const t of tagSet) {
          if (!leadTags.includes(t)) {
            ok = false;
            break;
          }
        }
        if (!ok) return false;
      }
      if (fitMin > 0 && (l.fit_score == null || l.fit_score < fitMin)) return false;
      if (hasEmailOnly && !l.email) return false;
      if (hasPhoneOnly && !l.phone) return false;
      if (q) {
        // Multi-field text match: name + email + phone + INN.
        // Phone is normalised to digits-only on both sides so users
        // can paste "+7 (495) 123-45-67" and still match "74951234567".
        const phoneDigits = q.replace(/\D/g, "");
        const leadName = (l.company_name ?? "").toLowerCase();
        const leadEmail = (l.email ?? "").toLowerCase();
        const leadInn = (l.inn ?? "").toLowerCase();
        const leadPhoneDigits = (l.phone ?? "").replace(/\D/g, "");
        const matched =
          leadName.includes(q) ||
          (leadEmail && leadEmail.includes(q)) ||
          (leadInn && leadInn.includes(q)) ||
          (phoneDigits.length >= 3 &&
            leadPhoneDigits &&
            leadPhoneDigits.includes(phoneDigits));
        if (!matched) return false;
      }
      return true;
    });
  }, [
    allItems,
    cityFilters,
    segmentFilters,
    priorityFilters,
    tierFilters,
    dealTypeFilters,
    sourceFilters,
    tagFilters,
    fitMin,
    search,
    hasEmailOnly,
    hasPhoneOnly,
  ]);

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
            <h1 className="type-page-title">База лидов</h1>
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
            <button
              onClick={() => setAiUpdateOpen(true)}
              className="inline-flex items-center gap-1.5 bg-canvas text-ink border border-black/10 rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-canvas-2 hover:border-black/20 active:scale-[0.98]"
              aria-label="Обновление через AI"
            >
              <Sparkles size={14} />
              AI Обновление
            </button>
            <ExportPopover
              filters={{
                city: cityFilters.length === 1 ? cityFilters[0] : undefined,
                segment:
                  segmentFilters.length === 1 ? segmentFilters[0] : undefined,
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
        <AIBulkUpdateModal
          open={aiUpdateOpen}
          onClose={() => setAiUpdateOpen(false)}
        />

        {/* Filter row — flex-wraps over 1-2 lines depending on viewport.
            Order: text search → categorical dropdowns → numeric/boolean
            modifiers → reset. Categorical filters that have nothing to
            offer (e.g. zero unique sources in the dataset) hide their
            dropdown to keep the bar from getting noisy. */}
        <div className="flex flex-wrap items-center gap-2 mt-3">
          {/* Search — name + email + phone + INN. */}
          <div className="relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-3 pointer-events-none"
            />
            <input
              type="text"
              placeholder="Поиск: имя, email, телефон, ИНН"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-sm bg-canvas border border-black/10 rounded-pill outline-none focus:border-brand-accent/40 focus:bg-white transition-all duration-300 w-64"
            />
          </div>

          <MultiSelectDropdown
            label="Сегмент"
            options={segments}
            selected={segmentFilters}
            onChange={setSegmentFilters}
            counts={segmentCounts}
          />

          <MultiSelectDropdown
            label="Город"
            options={cities}
            selected={cityFilters}
            onChange={setCityFilters}
            counts={cityCounts}
          />

          <MultiSelectDropdown
            label="Приоритет"
            options={PRIORITY_OPTIONS}
            selected={priorityFilters}
            onChange={setPriorityFilters}
            counts={priorityCounts}
          />

          <MultiSelectDropdown
            label="Tier"
            options={TIER_OPTIONS}
            selected={tierFilters}
            onChange={setTierFilters}
            counts={tierCounts}
          />

          {dealTypes.length > 0 && (
            <MultiSelectDropdown
              label="Тип сделки"
              options={dealTypes}
              selected={dealTypeFilters}
              onChange={setDealTypeFilters}
              counts={dealTypeCounts}
            />
          )}

          {sources.length > 0 && (
            <MultiSelectDropdown
              label="Источник"
              options={sources}
              selected={sourceFilters}
              onChange={setSourceFilters}
              counts={sourceCounts}
            />
          )}

          {tags.length > 0 && (
            <MultiSelectDropdown
              label="Теги"
              options={tags}
              selected={tagFilters}
              onChange={setTagFilters}
              counts={tagCounts}
            />
          )}

          <span className="text-muted-3 text-xs">|</span>

          <FitSlider value={fitMin} onChange={setFitMin} />

          <span className="text-muted-3 text-xs">|</span>

          {/* Boolean toggles — render as pill buttons with checked state. */}
          <button
            type="button"
            onClick={() => setHasEmailOnly((v) => !v)}
            aria-pressed={hasEmailOnly}
            className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-pill text-xs font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
              hasEmailOnly
                ? "bg-brand-soft text-brand-accent-text border-brand-accent/30"
                : "bg-canvas text-muted border-black/10 hover:border-black/20"
            }`}
          >
            С email
          </button>
          <button
            type="button"
            onClick={() => setHasPhoneOnly((v) => !v)}
            aria-pressed={hasPhoneOnly}
            className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-pill text-xs font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
              hasPhoneOnly
                ? "bg-brand-soft text-brand-accent-text border-brand-accent/30"
                : "bg-canvas text-muted border-black/10 hover:border-black/20"
            }`}
          >
            С телефоном
          </button>

          {activeFilterCount > 0 && (
            <>
              <span className="text-muted-3 text-xs">|</span>
              <button
                type="button"
                onClick={resetAllFilters}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-pill text-xs font-semibold text-rose hover:bg-rose/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose focus-visible:ring-offset-1"
              >
                <X size={12} />
                Сбросить ({activeFilterCount})
              </button>
            </>
          )}
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
              <p className="type-card-title mb-2">В пуле пока пусто</p>
              <p className="text-sm text-muted">
                Импортируйте лиды или добавьте вручную.
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
                      className="px-4 py-2.5 type-table-header text-muted-2 whitespace-nowrap"
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

