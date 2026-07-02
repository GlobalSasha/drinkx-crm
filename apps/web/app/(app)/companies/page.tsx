"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Search, X } from "lucide-react";
import { useCompanies } from "@/lib/hooks/use-companies";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import type { CompanyOut } from "@/lib/types";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/Empty";
import { MultiSelectDropdown } from "@/components/ui/MultiSelectDropdown";
import { segmentLabel } from "@/lib/i18n";

// Город/Сегмент/ИНН скрыты под md — на телефоне контекст идёт подстрокой
// в колонке «Название».
const HIDE_ON_MOBILE = {
  headerClassName: "hidden md:table-cell",
  cellClassName: "hidden md:table-cell",
};

const columns: ColumnDef<CompanyOut, unknown>[] = [
  {
    accessorKey: "name",
    header: "Название",
    cell: (info) => {
      const c = info.row.original;
      const sub = [c.city, c.primary_segment ? segmentLabel(c.primary_segment) : null]
        .filter(Boolean)
        .join(" · ");
      return (
        <div>
          <span className="type-body text-brand-accent font-medium">
            {(info.getValue() as string) || "—"}
          </span>
          {sub && (
            <p className="md:hidden type-caption text-brand-muted mt-0.5">{sub}</p>
          )}
        </div>
      );
    },
  },
  {
    accessorKey: "city",
    header: "Город",
    meta: HIDE_ON_MOBILE,
    cell: (info) => (
      <span className="type-caption text-brand-muted">
        {(info.getValue() as string | null) ?? "—"}
      </span>
    ),
  },
  {
    accessorKey: "primary_segment",
    header: "Сегмент",
    meta: HIDE_ON_MOBILE,
    cell: (info) => {
      const raw = info.getValue() as string | null;
      return (
        <span className="type-caption text-brand-muted">
          {raw ? segmentLabel(raw) : "—"}
        </span>
      );
    },
  },
  {
    accessorKey: "inn",
    header: "ИНН",
    meta: HIDE_ON_MOBILE,
    cell: (info) => (
      <span className="type-caption font-mono text-brand-muted">
        {(info.getValue() as string | null) ?? "—"}
      </span>
    ),
  },
];

export default function CompaniesPage() {
  const [search, setSearch] = useState("");
  const [cityFilters, setCityFilters] = useState<string[]>([]);
  const [segmentFilters, setSegmentFilters] = useState<string[]>([]);
  const router = useRouter();

  const { data, isLoading } = useCompanies();
  const allRows: CompanyOut[] = (data?.items ?? []).filter((c) => !c.is_archived);

  // Build dropdown option lists + counts from the unfiltered pool, so the
  // user can always see which segments/cities exist regardless of current
  // narrowing — same pattern as /leads-pool.
  const cityOptions = useMemo(
    () =>
      Array.from(new Set(allRows.map((c) => c.city).filter(Boolean) as string[])).sort(
        (a, b) => a.localeCompare(b),
      ),
    [allRows],
  );
  const segmentOptions = useMemo(
    () =>
      Array.from(
        new Set(
          allRows
            .map((c) => c.primary_segment)
            .filter(Boolean)
            // Translate slugs → human labels so the dropdown is consistent with /leads-pool
            .map((s) => segmentLabel(s as string)),
        ),
      ).sort((a, b) => a.localeCompare(b)),
    [allRows],
  );
  const cityCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of allRows) if (c.city) m[c.city] = (m[c.city] ?? 0) + 1;
    return m;
  }, [allRows]);
  const segmentCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of allRows) {
      if (!c.primary_segment) continue;
      const label = segmentLabel(c.primary_segment);
      m[label] = (m[label] ?? 0) + 1;
    }
    return m;
  }, [allRows]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const citySet = new Set(cityFilters);
    const segSet = new Set(segmentFilters);
    return allRows.filter((c) => {
      if (q) {
        const hit =
          c.name.toLowerCase().includes(q) ||
          (c.inn ?? "").toLowerCase().includes(q) ||
          (c.city ?? "").toLowerCase().includes(q);
        if (!hit) return false;
      }
      if (citySet.size > 0 && (!c.city || !citySet.has(c.city))) return false;
      if (segSet.size > 0) {
        // Filter values are human labels; translate the row's slug before comparing.
        if (!c.primary_segment) return false;
        if (!segSet.has(segmentLabel(c.primary_segment))) return false;
      }
      return true;
    });
  }, [allRows, search, cityFilters, segmentFilters]);

  const activeFilterCount =
    (search.trim() ? 1 : 0) + (cityFilters.length > 0 ? 1 : 0) + (segmentFilters.length > 0 ? 1 : 0);

  function resetFilters() {
    setSearch("");
    setCityFilters([]);
    setSegmentFilters([]);
  }

  return (
    <main className={pageContainerVariants({ surface: "data" })}>
      <PageHeader
        icon={<Building2 size={20} />}
        title="Компании"
        actions={
          <span className="type-caption text-brand-muted tabular-nums">
            {rows.length} из {allRows.length}
          </span>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-0 sm:min-w-[220px] max-w-md">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted pointer-events-none"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по названию, ИНН, городу"
            className="w-full pl-8 pr-3 py-2 type-caption bg-white border border-brand-border rounded-full outline-none focus:border-brand-accent"
          />
        </div>
        <MultiSelectDropdown
          label="Город"
          options={cityOptions}
          selected={cityFilters}
          onChange={setCityFilters}
          counts={cityCounts}
          emptyText="Нет городов"
        />
        <MultiSelectDropdown
          label="Сегмент"
          options={segmentOptions}
          selected={segmentFilters}
          onChange={setSegmentFilters}
          counts={segmentCounts}
          emptyText="Сегменты не заданы"
        />
        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={resetFilters}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full type-caption font-semibold text-brand-muted hover:text-brand-primary hover:bg-brand-panel transition-colors"
          >
            <X size={12} /> Сбросить
          </button>
        )}
      </div>

      {isLoading && rows.length === 0 ? (
        <p className="type-caption text-brand-muted py-6 text-center">Загрузка…</p>
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          rowKey={(r) => r.id}
          rowLabel={(r) => `Открыть карточку: ${r.name}`}
          onRowClick={(r) => {
            router.push(`/companies/${r.id}` as never);
          }}
          emptyState={
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Building2 />
                </EmptyMedia>
                <EmptyTitle>{search ? "Ничего не найдено" : "Компаний пока нет"}</EmptyTitle>
                <EmptyDescription>
                  {search
                    ? "Попробуйте другой запрос или очистите поиск."
                    : "Компании появятся здесь автоматически по мере появления лидов."}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          }
        />
      )}
    </main>
  );
}
