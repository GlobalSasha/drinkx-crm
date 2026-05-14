"use client";
import { useMemo } from "react";
import { Search, Plus, CalendarRange, Upload } from "lucide-react";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import { ExportPopover } from "@/components/export/ExportPopover";
import { PipelineSwitcher } from "@/components/pipeline/PipelineSwitcher";
import { MultiSelectDropdown } from "@/components/ui/MultiSelectDropdown";
import { SEGMENT_OPTIONS } from "@/lib/i18n";
import type { LeadOut } from "@/lib/types";

interface Props {
  leads: LeadOut[];
  totalCount: number;
}

export function PipelineHeader({ leads, totalCount }: Props) {
  const {
    filters,
    setSegments,
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
    <div className="flex flex-col gap-4 px-4 sm:px-6 py-4 bg-white border-b border-black/5">
      {/* Top row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 shrink-0">
          <h1 className="type-page-title">Воронка</h1>
          <span className="bg-black/5 text-muted-2 text-xs font-mono px-2 py-0.5 rounded-pill">
            {totalCount}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <PipelineSwitcher />
          <button
            onClick={openCreateLeadModal}
            className="inline-flex items-center gap-1.5 bg-brand-accent text-white rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-brand-accent/90 active:scale-[0.98]"
          >
            <Plus size={15} />
            Лид
          </button>
          <button
            onClick={openImportWizard}
            className="inline-flex items-center gap-1.5 bg-canvas text-ink border border-black/10 rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-canvas-2 hover:border-black/20 active:scale-[0.98]"
            aria-label="Импорт лидов из файла"
          >
            <Upload size={14} />
            Импорт
          </button>
          <ExportPopover
            filters={{
              segment: exportSegment,
              city: exportCity,
              q: filters.q || undefined,
              assignment_status: "assigned",
            }}
            leadCount={totalCount}
          />
          <button
            onClick={openSprintModal}
            className="inline-flex items-center gap-1.5 bg-transparent text-brand-accent border border-brand-accent/40 rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-brand-soft hover:border-brand-accent active:scale-[0.98]"
          >
            <CalendarRange size={15} />
            <span className="hidden sm:inline">Сформировать план на неделю</span>
            <span className="sm:hidden">План на неделю</span>
          </button>
        </div>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-3 pointer-events-none"
          />
          <input
            type="text"
            placeholder="Поиск..."
            value={filters.q}
            onChange={(e) => setQ(e.target.value)}
            className="h-8 pl-8 pr-3 text-sm bg-canvas border border-black/10 rounded-pill outline-none focus:border-brand-accent/40 focus:bg-white transition-all duration-300 w-44"
          />
        </div>

        <span className="text-muted-3 text-xs">|</span>

        <MultiSelectDropdown
          label="Сегмент"
          options={segmentOptions}
          selected={filters.segments}
          onChange={setSegments}
          counts={segmentCounts}
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
  );
}
