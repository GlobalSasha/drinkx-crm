"use client";
import { useState, useMemo, useCallback, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, Sparkles } from "lucide-react";
import { usePoolLeads, useClaimLead } from "@/lib/hooks/use-leads";
import { useForms } from "@/lib/hooks/use-forms";
import { Toast } from "@/components/ui/Toast";
import { ExportPopover } from "@/components/export/ExportPopover";
import { AIBulkUpdateModal } from "@/components/export/AIBulkUpdateModal";
import { PoolRow } from "@/components/leads-pool/PoolRow";
import { PoolFilterBar } from "@/components/leads-pool/PoolFilterBar";
import { tierFromScore } from "@/lib/types";
import { SEGMENT_OPTIONS } from "@/lib/i18n";

// ---- Toast state ----

interface ToastState {
  id: number;
  message: string;
  type: "error" | "success";
}

// ---- Page ----

function LeadsPoolPageInner() {
  const searchParams = useSearchParams();
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
  const [formId, setFormId] = useState<string | undefined>(undefined);
  const [needsReview, setNeedsReview] = useState<boolean | undefined>(undefined);
  const [toasts, setToasts] = useState<ToastState[]>([]);
  // Track which lead IDs are currently being claimed (for optimistic UI)
  const [claimingIds, setClaimingIds] = useState<Set<string>>(new Set());
  const [aiUpdateOpen, setAiUpdateOpen] = useState(false);

  // Pre-select form filter from ?form_id= URL param (set by Lead Card chip links).
  const didMountRef = useRef(false);
  useEffect(() => {
    if (didMountRef.current) return;
    didMountRef.current = true;
    const presetFormId = searchParams.get("form_id") ?? undefined;
    if (presetFormId) setFormId(presetFormId);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
    (hasPhoneOnly ? 1 : 0) +
    (formId ? 1 : 0) +
    (needsReview !== undefined ? 1 : 0);

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
    setFormId(undefined);
    setNeedsReview(undefined);
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
  // form_id is server-side filtered because it scopes the whole pool
  // to a specific landing source.
  const poolQuery = usePoolLeads({ page_size: 500, form_id: formId, needs_review: needsReview });
  const claimMutation = useClaimLead();

  const formsQuery = useForms();
  const forms = formsQuery.data?.items ?? [];

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
      <div className="sticky top-0 z-10 bg-white border-b border-brand-border px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-baseline gap-2">
            <h1 className="type-page-title">База лидов</h1>
            {/* Compact total — shown small next to title, the loud counts
                live inside each chip below. */}
            <span className="text-brand-muted text-xs font-mono tabular-nums">
              {filtered.length}
              {filtered.length !== allItems.length && (
                <span className="text-brand-muted"> / {allItems.length}</span>
              )}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setAiUpdateOpen(true)}
              className="inline-flex items-center gap-1.5 bg-brand-bg text-brand-primary border border-brand-border rounded-full px-4 py-2 text-sm font-semibold transition hover:bg-brand-panel active:scale-[0.96]"
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
              <span className="text-xs font-semibold text-brand-muted">Только мой пул</span>
              <div className="w-8 h-4 rounded-full bg-black/10" />
            </label>
          </div>
        </div>
        <AIBulkUpdateModal
          open={aiUpdateOpen}
          onClose={() => setAiUpdateOpen(false)}
        />

        <PoolFilterBar
          search={search}
          setSearch={setSearch}
          segments={segments}
          segmentFilters={segmentFilters}
          setSegmentFilters={setSegmentFilters}
          segmentCounts={segmentCounts}
          cities={cities}
          cityFilters={cityFilters}
          setCityFilters={setCityFilters}
          cityCounts={cityCounts}
          priorityFilters={priorityFilters}
          setPriorityFilters={setPriorityFilters}
          priorityCounts={priorityCounts}
          tierFilters={tierFilters}
          setTierFilters={setTierFilters}
          tierCounts={tierCounts}
          dealTypes={dealTypes}
          dealTypeFilters={dealTypeFilters}
          setDealTypeFilters={setDealTypeFilters}
          dealTypeCounts={dealTypeCounts}
          sources={sources}
          sourceFilters={sourceFilters}
          setSourceFilters={setSourceFilters}
          sourceCounts={sourceCounts}
          forms={forms}
          formId={formId}
          setFormId={setFormId}
          needsReview={needsReview}
          setNeedsReview={setNeedsReview}
          tags={tags}
          tagFilters={tagFilters}
          setTagFilters={setTagFilters}
          tagCounts={tagCounts}
          fitMin={fitMin}
          setFitMin={setFitMin}
          hasEmailOnly={hasEmailOnly}
          setHasEmailOnly={setHasEmailOnly}
          hasPhoneOnly={hasPhoneOnly}
          setHasPhoneOnly={setHasPhoneOnly}
          activeFilterCount={activeFilterCount}
          resetAllFilters={resetAllFilters}
        />
      </div>

      {/* Body */}
      <div className="px-6 py-6">
        {isLoading && (
          <div className="flex items-center justify-center py-20 gap-2 text-brand-muted text-sm">
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
            <div className="bg-white border border-brand-border rounded-card p-10 max-w-sm w-full">
              <p className="type-card-title mb-2">В пуле пока пусто</p>
              <p className="text-sm text-brand-muted">
                Импортируйте лиды или добавьте вручную.
              </p>
            </div>
          </div>
        )}

        {!isLoading && !isError && filtered.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-brand-border bg-white">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-brand-border">
                  {/* Город/Сегмент/Fit/Статус уходят под md: на телефоне они
                      показываются подстрокой в первой ячейке PoolRow. */}
                  {[
                    { h: "Компания", cls: "" },
                    { h: "Город", cls: "hidden md:table-cell" },
                    { h: "Сегмент", cls: "hidden md:table-cell" },
                    { h: "Tier", cls: "" },
                    { h: "Fit Score", cls: "hidden md:table-cell" },
                    { h: "Статус", cls: "hidden md:table-cell" },
                    { h: "", cls: "" },
                  ].map(({ h, cls }) => (
                    <th
                      key={h}
                      className={`px-4 py-2.5 type-table-header text-brand-muted whitespace-nowrap ${cls}`}
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

// useSearchParams requires a Suspense boundary in Next 15 App Router.
export default function LeadsPoolPage() {
  return (
    <Suspense fallback={null}>
      <LeadsPoolPageInner />
    </Suspense>
  );
}

