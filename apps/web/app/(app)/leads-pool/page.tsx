"use client";
import { useState, useMemo, useCallback, useEffect, useRef, Suspense } from "react";
import type { SetStateAction } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, ShieldAlert, Sparkles } from "lucide-react";
import {
  POOL_PAGE_SIZE,
  useClaimLead,
  usePoolFacets,
  usePoolLeads,
} from "@/lib/hooks/use-leads";
import {
  activeFilterCount,
  poolFilterBody,
  EMPTY_POOL_FILTERS,
  type PoolFilterState,
} from "@/lib/leads-pool-filters";
import { useForms } from "@/lib/hooks/use-forms";
import { useMe } from "@/lib/hooks/use-me";
import { Toast } from "@/components/ui/Toast";
import { ExportPopover } from "@/components/export/ExportPopover";
import { AIBulkUpdateModal } from "@/components/export/AIBulkUpdateModal";
import { PoolRow } from "@/components/leads-pool/PoolRow";
import { PoolFilterBar } from "@/components/leads-pool/PoolFilterBar";
import { SelectionBar } from "@/components/leads-pool/SelectionBar";
import { AssignLeadsModal } from "@/components/leads-pool/AssignLeadsModal";
import type { FacetValue, LeadAssignOut } from "@/lib/types";
import { SEGMENT_OPTIONS } from "@/lib/i18n";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "@/components/ui/Empty";

/** Задержка перед отправкой поискового запроса на сервер. */
const SEARCH_DEBOUNCE_MS = 300;

// ---- Toast state ----

interface ToastState {
  id: number;
  message: string;
  type: "error" | "success";
}

// ---- Page ----

function LeadsPoolPageInner() {
  const searchParams = useSearchParams();
  // Одно состояние фильтров вместо тринадцати отдельных: оно же уходит в
  // список, в счётчики, в экспорт и в выдачу «по фильтру» (аудит G6).
  const [filters, setFilters] = useState<PoolFilterState>(EMPTY_POOL_FILTERS);
  // Текст в поле ввода отделён от того, что ушло на сервер: запрос
  // отправляется с задержкой, иначе каждое нажатие — обращение к базе.
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [toasts, setToasts] = useState<ToastState[]>([]);
  // Track which lead IDs are currently being claimed (for optimistic UI)
  const [claimingIds, setClaimingIds] = useState<Set<string>>(new Set());
  const [aiUpdateOpen, setAiUpdateOpen] = useState(false);
  // G2: выделение карточек руководителем для выдачи менеджеру.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [assignMode, setAssignMode] = useState<"selected" | "topN" | null>(null);

  const meQuery = useMe();
  const canAssign = meQuery.data?.role === "admin" || meQuery.data?.role === "head";

  /** Любая смена условия возвращает на первую страницу. */
  const updateFilters = useCallback(
    (patch: Partial<PoolFilterState>) => {
      setFilters((prev) => ({ ...prev, ...patch }));
      setPage(1);
    },
    [],
  );

  /**
   * Сеттер одного поля фильтра в форме, к которой привыкли компоненты
   * фильтров: принимает и значение, и функцию-обновитель.
   */
  const setField = useCallback(
    <K extends keyof PoolFilterState>(key: K) =>
      (value: SetStateAction<PoolFilterState[K]>) => {
        setFilters((prev) => ({
          ...prev,
          [key]:
            typeof value === "function"
              ? (value as (p: PoolFilterState[K]) => PoolFilterState[K])(prev[key])
              : value,
        }));
        setPage(1);
      },
    [],
  );

  // Ввод в поиске уходит на сервер с задержкой.
  useEffect(() => {
    const id = setTimeout(() => {
      setFilters((prev) =>
        prev.search === searchInput ? prev : { ...prev, search: searchInput },
      );
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [searchInput]);

  // Pre-select form filter from ?form_id= URL param (set by Lead Card chip links).
  const didMountRef = useRef(false);
  useEffect(() => {
    if (didMountRef.current) return;
    didMountRef.current = true;
    const presetFormId = searchParams.get("form_id") ?? undefined;
    if (presetFormId) setFilters((prev) => ({ ...prev, formId: presetFormId }));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const activeFilters = activeFilterCount(filters);

  function resetAllFilters() {
    setFilters(EMPTY_POOL_FILTERS);
    setSearchInput("");
    setPage(1);
  }

  // Monotonic toast id — avoids React key collisions when two toasts are
  // created within the same millisecond (plan 026). Date.now() could collide.
  const toastSeqRef = useRef(0);
  const addToast = useCallback((message: string, type: "error" | "success" = "success") => {
    const id = toastSeqRef.current++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  // Список и счётчики приходят с сервера. Раньше здесь запрашивались 500
  // карточек, а всё остальное — поиск, приоритет, tier, тип сделки,
  // источник, теги, наличие почты и телефона — решал `Array.filter` по
  // этим строкам. Карточка за границей не находилась ничем, счётчики в
  // выпадающих списках описывали загруженный кусок, а экспорт получал
  // урезанный набор полей (аудит G6).
  const poolQuery = usePoolLeads(filters, page);
  const facetsQuery = usePoolFacets(filters);
  const { mutate: claimLead } = useClaimLead();

  const formsQuery = useForms();
  const forms = formsQuery.data?.items ?? [];

  const rows = poolQuery.data?.items ?? [];
  const total = poolQuery.data?.total ?? 0;
  const pageSize = poolQuery.data?.page_size ?? POOL_PAGE_SIZE;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const facets = facetsQuery.data;

  // Значения для выпадающих списков и числа рядом с ними — из ответа
  // сервера, а не из загруженных строк. Сегменты дополняем канонической
  // русской раскладкой, как и раньше: набор не должен зависеть от того,
  // что сейчас лежит в базе.
  const facetValues = useCallback(
    (list: FacetValue[] | undefined) => (list ?? []).map((f) => f.value),
    [],
  );
  const facetCounts = useCallback(
    (list: FacetValue[] | undefined) =>
      Object.fromEntries((list ?? []).map((f) => [f.value, f.count])),
    [],
  );

  const cities = useMemo(() => facetValues(facets?.cities), [facets, facetValues]);
  const segments = useMemo(() => {
    const extras = facetValues(facets?.segments).filter(
      (s) => !SEGMENT_OPTIONS.includes(s as typeof SEGMENT_OPTIONS[number]),
    );
    return [...SEGMENT_OPTIONS, ...extras.sort()];
  }, [facets, facetValues]);
  const dealTypes = useMemo(() => facetValues(facets?.deal_types), [facets, facetValues]);
  const sources = useMemo(() => facetValues(facets?.sources), [facets, facetValues]);
  const tags = useMemo(() => facetValues(facets?.tags), [facets, facetValues]);

  const cityCounts = useMemo(() => facetCounts(facets?.cities), [facets, facetCounts]);
  const segmentCounts = useMemo(() => facetCounts(facets?.segments), [facets, facetCounts]);
  const priorityCounts = useMemo(() => facetCounts(facets?.priorities), [facets, facetCounts]);
  const tierCounts = useMemo(() => facetCounts(facets?.tiers), [facets, facetCounts]);
  const dealTypeCounts = useMemo(() => facetCounts(facets?.deal_types), [facets, facetCounts]);
  const sourceCounts = useMemo(() => facetCounts(facets?.sources), [facets, facetCounts]);
  const tagCounts = useMemo(() => facetCounts(facets?.tags), [facets, facetCounts]);

  // Выделение считается только по видимым строкам: руководитель не должен
  // выдать то, чего сейчас не видит.
  const visibleSelected = useMemo(
    () => rows.filter((l) => selectedIds.has(l.id)).map((l) => l.id),
    [rows, selectedIds],
  );

  // Вычищаем из выделения id карточек, которых больше нет в пуле —
  // например, после выдачи или после того, как менеджер взял карточку.
  useEffect(() => {
    setSelectedIds((prev) => {
      if (prev.size === 0) return prev;
      const poolIds = new Set(rows.map((l) => l.id));
      let changed = false;
      const next = new Set<string>();
      for (const id of prev) {
        if (poolIds.has(id)) {
          next.add(id);
        } else {
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [rows]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const allFilteredSelected = rows.length > 0 && rows.every((l) => selectedIds.has(l.id));
  const someFilteredSelected = !allFilteredSelected && rows.some((l) => selectedIds.has(l.id));
  const selectAllRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someFilteredSelected;
  }, [someFilteredSelected]);

  function toggleSelectAll() {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        for (const l of rows) next.delete(l.id);
      } else {
        for (const l of rows) next.add(l.id);
      }
      return next;
    });
  }

  function handleAssignDone(result: LeadAssignOut, recipientName: string) {
    if (result.assigned_count === result.requested) {
      addToast(`Выдано карточек: ${result.assigned_count} · ${recipientName}`, "success");
    } else if (result.assigned_count > 0) {
      addToast(
        `Выдано ${result.assigned_count} из ${result.requested} · ${recipientName}. Остальные уже разобрали`,
        "success",
      );
    } else {
      addToast("Не выдано ни одной карточки: подходящих в пуле не осталось", "error");
    }
    setSelectedIds(new Set());
  }

  const handleClaim = useCallback((id: string) => {
    // Optimistic: gray row immediately
    setClaimingIds((prev) => new Set(prev).add(id));

    claimLead(id, {
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
  }, [addToast, claimLead]);

  const isLoading = poolQuery.isLoading;
  const isError = poolQuery.isError;
  // Plan 026: the pool is fetched in one page; if the server has more leads
  // than we received, the table + every chip count are based on a partial
  // pool. Surface that instead of silently hiding leads. (Full server-side
  // filtering + facet counts is the tracked follow-up.)
  const rangeFrom = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeTo = Math.min(page * pageSize, total);

  // Пул — только руководителю и админу (доступ урезан 2026-09-14). Пункт меню
  // у менеджера скрыт, но по прямой ссылке страница открывалась и валилась
  // ошибкой API — вместо неё объясняющий экран.
  if (meQuery.isLoading || !meQuery.data) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 size={20} className="animate-spin text-brand-muted" />
      </div>
    );
  }
  if (meQuery.data.role !== "admin" && meQuery.data.role !== "head") {
    return (
      <div className={pageContainerVariants({ surface: "reading" })}>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><ShieldAlert /></EmptyMedia>
            <EmptyTitle>Раздел «База лидов»</EmptyTitle>
            <EmptyDescription>
              Базу лидов раздаёт руководитель: новые карточки придут к вам сами
              и будут ждать в разделе «Сегодня».
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Link
              href="/today"
              className="inline-flex items-center gap-2 text-sm font-medium text-brand-accent-text hover:underline"
            >
              ← Вернуться на «Сегодня»
            </Link>
          </EmptyContent>
        </Empty>
      </div>
    );
  }

  return (
    <>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b border-brand-border px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-baseline gap-2">
            <h1 className="type-page-title">База лидов</h1>
            {/* Compact total — shown small next to title, the loud counts
                live inside each chip below. */}
            <span className="text-brand-muted text-xs font-mono tabular-nums">
              {/* Число с сервера: столько карточек подходит под фильтры
                  целиком, а не столько загружено. */}
              {total > 0 ? `${rangeFrom}–${rangeTo} из ${total}` : total}
            </span>
            {/* Предупреждения «показаны первые N из M» больше нет: список
                листается страницами, а фильтры и поиск применяются ко всей
                базе, а не к загруженному куску. */}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setAiUpdateOpen(true)}
              className="inline-flex items-center gap-1.5 bg-brand-bg text-brand-primary border border-brand-border rounded-full px-4 py-2 text-sm font-semibold transition hover:bg-brand-panel active:scale-[0.96]"
              aria-label="Обновление через AI"
            >
              <Sparkles size={14} />
              AI Обновление
            </button>
            {canAssign && !isLoading && !isError && (
              <button
                onClick={() => setAssignMode("topN")}
                disabled={total === 0}
                className="inline-flex items-center gap-1.5 bg-brand-bg text-brand-primary border border-brand-border rounded-full px-4 py-2 text-sm font-semibold transition hover:bg-brand-panel active:scale-[0.96] disabled:opacity-40"
              >
                Выдать по фильтру
              </button>
            )}
            {/* Тот же объект выборки, что у списка. Раньше сюда уходили
                город и сегмент только когда выбран ровно один, а
                приоритет, tier, теги, источник и галочки почты с
                телефоном не уходили вовсе — выгрузка не совпадала с
                экраном (аудит G6). */}
            <ExportPopover filters={poolFilterBody(filters)} leadCount={total} />
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
          search={searchInput}
          setSearch={setSearchInput}
          segments={segments}
          segmentFilters={filters.segments}
          setSegmentFilters={setField("segments")}
          segmentCounts={segmentCounts}
          cities={cities}
          cityFilters={filters.cities}
          setCityFilters={setField("cities")}
          cityCounts={cityCounts}
          priorityFilters={filters.priorities}
          setPriorityFilters={setField("priorities")}
          priorityCounts={priorityCounts}
          tierFilters={filters.tiers}
          setTierFilters={setField("tiers")}
          tierCounts={tierCounts}
          dealTypes={dealTypes}
          dealTypeFilters={filters.dealTypes}
          setDealTypeFilters={setField("dealTypes")}
          dealTypeCounts={dealTypeCounts}
          sources={sources}
          sourceFilters={filters.sources}
          setSourceFilters={setField("sources")}
          sourceCounts={sourceCounts}
          forms={forms}
          formId={filters.formId}
          setFormId={setField("formId")}
          needsReview={filters.needsReview}
          setNeedsReview={setField("needsReview")}
          tags={tags}
          tagFilters={filters.tags}
          setTagFilters={setField("tags")}
          tagCounts={tagCounts}
          fitMin={filters.fitMin}
          setFitMin={setField("fitMin")}
          hasEmailOnly={filters.hasEmail}
          setHasEmailOnly={setField("hasEmail")}
          hasPhoneOnly={filters.hasPhone}
          setHasPhoneOnly={setField("hasPhone")}
          activeFilterCount={activeFilters}
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

        {!isLoading && !isError && total === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="bg-white border border-brand-border rounded-card p-10 max-w-sm w-full">
              <p className="type-card-title mb-2">
                {activeFilters > 0 ? "Ничего не найдено" : "В пуле пока пусто"}
              </p>
              <p className="text-sm text-brand-muted">
                {activeFilters > 0
                  ? "Под эти условия в базе нет ни одной карточки. Снимите часть фильтров."
                  : "Импортируйте лиды или добавьте вручную."}
              </p>
            </div>
          </div>
        )}

        {!isLoading && !isError && total > 0 && (
          <>
            <div className="overflow-x-auto rounded-xl border border-brand-border bg-white">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-brand-border">
                    {canAssign && (
                      <th className="px-3 py-2.5">
                        <input
                          ref={selectAllRef}
                          type="checkbox"
                          checked={allFilteredSelected}
                          onChange={toggleSelectAll}
                          aria-label="Выбрать все в списке"
                          className="h-4 w-4 accent-brand-accent"
                        />
                      </th>
                    )}
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
                  {rows.map((lead) => (
                    <PoolRow
                      key={lead.id}
                      lead={lead}
                      onClaim={handleClaim}
                      claiming={claimingIds.has(lead.id)}
                      selectable={canAssign}
                      selected={selectedIds.has(lead.id)}
                      onToggleSelect={toggleSelect}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            {/* Страницы. Вся база в браузер не загружается: фильтры и
                поиск применяются на сервере, сюда приезжает одна
                страница. */}
            {pageCount > 1 && (
              <nav
                className="mt-4 flex items-center justify-between gap-3"
                aria-label="Страницы базы лидов"
              >
                <span className="text-xs text-brand-muted font-mono tabular-nums">
                  {rangeFrom}–{rangeTo} из {total}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1 || poolQuery.isFetching}
                    className="rounded-full border border-brand-border px-3 py-1.5 text-xs font-semibold disabled:opacity-40"
                  >
                    Назад
                  </button>
                  <span className="text-xs text-brand-muted font-mono tabular-nums">
                    {page} / {pageCount}
                  </span>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                    disabled={page >= pageCount || poolQuery.isFetching}
                    className="rounded-full border border-brand-border px-3 py-1.5 text-xs font-semibold disabled:opacity-40"
                  >
                    Вперёд
                  </button>
                </div>
              </nav>
            )}
            {canAssign && visibleSelected.length > 0 && (
              <SelectionBar
                count={visibleSelected.length}
                onAssign={() => setAssignMode("selected")}
                onClear={() => setSelectedIds(new Set())}
              />
            )}
          </>
        )}
      </div>

      {canAssign && assignMode && (
        <AssignLeadsModal
          open
          onClose={() => setAssignMode(null)}
          mode={assignMode}
          selectedIds={visibleSelected}
          /* «по фильтру» отправляет на сервер саму выборку и её размер, а
             не список id с текущей страницы (аудит G6). */
          filterBody={poolFilterBody(filters)}
          matchingCount={total}
          onDone={handleAssignDone}
        />
      )}

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
