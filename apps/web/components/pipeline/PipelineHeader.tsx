"use client";
import { Search, Plus, CalendarRange } from "lucide-react";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import type { LeadOut } from "@/lib/types";

const SEGMENTS = [
  "HoReCa",
  "Офисы",
  "Ритейл",
  "Производство",
  "Образование",
  "Медицина",
];

interface Props {
  leads: LeadOut[];
  totalCount: number;
}

export function PipelineHeader({ leads, totalCount }: Props) {
  const { filters, setSegment, setCity, setQ, openSprintModal, openCreateLeadModal } =
    usePipelineStore();

  // Unique cities from the current lead set
  const cities = Array.from(
    new Set(leads.map((l) => l.city).filter(Boolean) as string[])
  ).sort();

  return (
    <div className="flex flex-col gap-3 px-4 sm:px-6 py-4 bg-white border-b border-black/5">
      {/* Top row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 shrink-0">
          <h1 className="text-xl font-extrabold tracking-tight">Pipeline</h1>
          <span className="bg-black/5 text-muted-2 text-xs font-mono px-2 py-0.5 rounded-pill">
            {totalCount}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={openCreateLeadModal}
            className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-ink/90 active:scale-[0.98]"
          >
            <Plus size={15} />
            Лид
          </button>
          <button
            onClick={openSprintModal}
            className="inline-flex items-center gap-1.5 bg-accent text-white rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-accent/90 active:scale-[0.98]"
          >
            <CalendarRange size={15} />
            <span className="hidden sm:inline">Сформировать план на неделю</span>
            <span className="sm:hidden">План на неделю</span>
          </button>
        </div>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Search */}
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
            className="pl-8 pr-3 py-1.5 text-sm bg-canvas border border-black/10 rounded-pill outline-none focus:border-accent/40 focus:bg-white transition-all duration-300 w-44"
          />
        </div>

        <span className="text-muted-3 text-xs">|</span>

        {/* Segment chips */}
        <ChipGroup
          label="Все"
          options={SEGMENTS}
          selected={filters.segment}
          onSelect={setSegment}
        />

        {cities.length > 0 && (
          <>
            <span className="text-muted-3 text-xs">|</span>
            <ChipGroup
              label="Все города"
              options={cities}
              selected={filters.city}
              onSelect={setCity}
            />
          </>
        )}
      </div>
    </div>
  );
}

function ChipGroup({
  label,
  options,
  selected,
  onSelect,
}: {
  label: string;
  options: string[];
  selected: string | null;
  onSelect: (v: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      <Chip active={selected === null} onClick={() => onSelect(null)}>
        {label}
      </Chip>
      {options.map((o) => (
        <Chip key={o} active={selected === o} onClick={() => onSelect(o)}>
          {o}
        </Chip>
      ))}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded-pill text-xs font-semibold transition-all duration-300 ${
        active
          ? "bg-accent text-white"
          : "bg-canvas text-muted hover:bg-canvas-2"
      }`}
    >
      {children}
    </button>
  );
}
