"use client";
import { useMe } from "@/lib/hooks/use-me";
import { useMemo } from "react";
import { Search, Plus, CalendarRange, Upload } from "lucide-react";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import { ExportPopover } from "@/components/export/ExportPopover";
import { PipelineSwitcher } from "@/components/pipeline/PipelineSwitcher";
import { MultiSelectDropdown } from "@/components/ui/MultiSelectDropdown";
import { SEGMENT_OPTIONS } from "@/lib/i18n";
import { Button } from "@/components/ui/Button";
import { C } from "@/lib/design-system";
import type { LeadListItem } from "@/lib/types";

interface Props {
  leads: LeadListItem[];
  totalCount: number;
}

export function PipelineHeader({ leads, totalCount }: Props) {
  const { data: me } = useMe();
  const isAdminOrHead = me?.role === "admin" || me?.role === "head";
  const {
    filters,
    setSegments,
    setCountries,
    setCities,
    setQ,
    openSprintModal,
    openCreateLeadModal,
    openImportWizard,
  } = usePipelineStore();

  // Per-segment / per-city counts on the unfiltered set, so dropdown rows
  // can show how many leads sit behind each option.
  const segmentCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of leads) {
      if (l.segment) m[l.segment] = (m[l.segment] ?? 0) + 1;
    }
    return m;
  }, [leads]);

  const countryCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of leads) {
      if (l.country) m[l.country] = (m[l.country] ?? 0) + 1;
    }
    return m;
  }, [leads]);

  const cityCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of leads) {
      if (l.city) m[l.city] = (m[l.city] ?? 0) + 1;
    }
    return m;
  }, [leads]);

  // Segment options: canonical list + anything unexpected that's already
  // sitting in the data (legacy values, freshly imported leads).
  const segmentOptions = useMemo(() => {
    const extras = new Set<string>();
    for (const l of leads) {
      if (l.segment && !SEGMENT_OPTIONS.includes(l.segment as typeof SEGMENT_OPTIONS[number])) {
        extras.add(l.segment);
      }
    }
    return [...SEGMENT_OPTIONS, ...Array.from(extras).sort()];
  }, [leads]);

  const countryOptions = useMemo(
    () =>
      Array.from(new Set(leads.map((l) => l.country).filter(Boolean) as string[])).sort(
        (a, b) => a.localeCompare(b, "ru"),
      ),
    [leads],
  );

  const cityOptions = useMemo(
    () =>
      Array.from(new Set(leads.map((l) => l.city).filter(Boolean) as string[])).sort(
        (a, b) => a.localeCompare(b, "ru"),
      ),
    [leads],
  );

  // Export dropdown still expects a single segment/city. Degrade gracefully:
  // pass the value through only when exactly one option is selected.
  const exportSegment =
    filters.segments.length === 1 ? filters.segments[0] : undefined;
  const exportCity =
    filters.cities.length === 1 ? filters.cities[0] : undefined;

  return (
    <div className="flex flex-col gap-4 px-4 sm:px-6 py-4 bg-white border-b border-brand-border">
      {/* Top row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 shrink-0">
          <h1 className="type-page-title">Воронка</h1>
          <span className="bg-black/5 text-brand-muted text-xs font-mono px-2 py-0.5 rounded-full">
            {totalCount}
          </span>
        </div>

        {/* Phone: one row — pipeline name left, actions right, «План» as an icon. */}
        <div className="flex items-center gap-2 w-full md:w-auto md:flex-wrap">
          <div className="min-w-0 mr-auto md:mr-0">
            <PipelineSwitcher />
          </div>
          <Button
            variant="primary"
            onClick={openCreateLeadModal}
            className="font-semibold"
          >
            <Plus size={15} />
            Лид
          </Button>
          <button
            onClick={openImportWizard}
            // Import/export are desk work — hidden on a phone to give the list room.
            className={`hidden md:inline-flex items-center gap-1.5 bg-brand-bg text-brand-primary border border-brand-border rounded-full px-4 py-2 text-sm font-semibold transition hover:bg-brand-panel active:scale-[0.96] ${C.focusRing}`}
            aria-label="Импорт лидов из файла"
          >
            <Upload size={14} />
            Импорт
          </button>
          <div className="hidden md:block">
          <ExportPopover
            filters={{
              segment: exportSegment,
              city: exportCity,
              q: filters.q || undefined,
              assignment_status: "assigned",
            }}
            leadCount={totalCount}
          />
          </div>
        {isAdminOrHead && (
          <Button
            variant="ghost"
            onClick={openSprintModal}
            aria-label="Сформировать план на неделю"
            title="Сформировать план на неделю"
            className="text-brand-accent border-brand-accent/40 font-semibold hover:bg-brand-soft hover:border-brand-accent"
          >
            <CalendarRange size={15} />
            <span className="hidden sm:inline">Сформировать план на неделю</span>
          </Button>
        )}
        </div>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 md:flex-none">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted pointer-events-none"
          />
          <input
            type="text"
            placeholder="Поиск..."
            value={filters.q}
            onChange={(e) => setQ(e.target.value)}
            className="h-8 pl-8 pr-3 text-sm bg-brand-bg border border-brand-border rounded-full outline-none focus:border-brand-accent/40 focus:bg-white transition duration-300 w-full md:w-44"
          />
        </div>

        {/* Segment/city filters: desktop only — on a phone the stage chips
            and «Срочные» in the list do the narrowing. */}
        <div className="hidden md:contents">
        <MultiSelectDropdown
          label="Сегмент"
          options={segmentOptions}
          selected={filters.segments}
          onChange={setSegments}
          counts={segmentCounts}
        />

        <MultiSelectDropdown
          label="Страна"
          options={countryOptions}
          selected={filters.countries}
          onChange={setCountries}
          counts={countryCounts}
        />

        <MultiSelectDropdown
          label="Город"
          options={cityOptions}
          selected={filters.cities}
          onChange={setCities}
          counts={cityCounts}
        />
        </div>
      </div>
    </div>
  );
}
