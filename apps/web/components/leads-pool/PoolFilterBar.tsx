"use client";

import { useId, useState } from "react";
import { ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import { MultiSelectDropdown } from "@/components/ui/MultiSelectDropdown";
import { FitSlider } from "@/components/leads-pool/FitSlider";
import type { WebFormOut } from "@/lib/types";

const TIER_OPTIONS = ["A", "B", "C", "D"];
const PRIORITY_OPTIONS = ["A", "B", "C", "D"];

interface Props {
  search: string;
  setSearch: (v: string) => void;
  segments: string[];
  segmentFilters: string[];
  setSegmentFilters: (v: string[]) => void;
  segmentCounts: Record<string, number>;
  cities: string[];
  cityFilters: string[];
  setCityFilters: (v: string[]) => void;
  cityCounts: Record<string, number>;
  priorityFilters: string[];
  setPriorityFilters: (v: string[]) => void;
  priorityCounts: Record<string, number>;
  tierFilters: string[];
  setTierFilters: (v: string[]) => void;
  tierCounts: Record<string, number>;
  dealTypes: string[];
  dealTypeFilters: string[];
  setDealTypeFilters: (v: string[]) => void;
  dealTypeCounts: Record<string, number>;
  sources: string[];
  sourceFilters: string[];
  setSourceFilters: (v: string[]) => void;
  sourceCounts: Record<string, number>;
  forms: WebFormOut[];
  formId: string | undefined;
  setFormId: (v: string | undefined) => void;
  needsReview: boolean | undefined;
  setNeedsReview: (v: boolean | undefined | ((prev: boolean | undefined) => boolean | undefined)) => void;
  tags: string[];
  tagFilters: string[];
  setTagFilters: (v: string[]) => void;
  tagCounts: Record<string, number>;
  fitMin: number;
  setFitMin: (v: number) => void;
  hasEmailOnly: boolean;
  setHasEmailOnly: (v: boolean | ((prev: boolean) => boolean)) => void;
  hasPhoneOnly: boolean;
  setHasPhoneOnly: (v: boolean | ((prev: boolean) => boolean)) => void;
  activeFilterCount: number;
  selectedFilterCount: number;
  resetAllFilters: () => void;
}

// ---- Two filter rows: search/categories, then additional conditions.
// Order: text search → categorical dropdowns → numeric/boolean
// modifiers → reset. Categorical filters that have nothing to
// offer (e.g. zero unique sources in the dataset) hide their
// dropdown to keep the bar from getting noisy. ----

export function PoolFilterBar({
  search,
  setSearch,
  segments,
  segmentFilters,
  setSegmentFilters,
  segmentCounts,
  cities,
  cityFilters,
  setCityFilters,
  cityCounts,
  priorityFilters,
  setPriorityFilters,
  priorityCounts,
  tierFilters,
  setTierFilters,
  tierCounts,
  dealTypes,
  dealTypeFilters,
  setDealTypeFilters,
  dealTypeCounts,
  sources,
  sourceFilters,
  setSourceFilters,
  sourceCounts,
  forms,
  formId,
  setFormId,
  needsReview,
  setNeedsReview,
  tags,
  tagFilters,
  setTagFilters,
  tagCounts,
  fitMin,
  setFitMin,
  hasEmailOnly,
  setHasEmailOnly,
  hasPhoneOnly,
  setHasPhoneOnly,
  activeFilterCount,
  selectedFilterCount,
  resetAllFilters,
}: Props) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();

  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-3">
      {/* Search — name + email + phone + INN. */}
      <div className="relative min-w-0 flex-1 lg:w-80 lg:flex-none">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted pointer-events-none"
        />
        <input
          type="text"
          aria-label="Поиск по базе лидов"
          placeholder="Поиск: имя, email, телефон, ИНН"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8 pr-3 h-10 text-sm bg-brand-bg border border-brand-border rounded-full outline-none focus:border-brand-accent/40 focus:bg-white transition duration-300 w-full"
        />
      </div>

      <button
        type="button"
        aria-label={`Фильтры (${selectedFilterCount})`}
        aria-expanded={filtersOpen}
        aria-controls={filtersId}
        onClick={() => setFiltersOpen((open) => !open)}
        className="inline-flex h-10 shrink-0 items-center gap-2 rounded-full border border-brand-border bg-brand-bg px-3 text-sm font-semibold text-brand-primary hover:bg-brand-panel focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 lg:hidden"
      >
        <SlidersHorizontal size={14} aria-hidden="true" />
        Фильтры
        <span className={`rounded-full px-2 text-xs tabular-nums ${selectedFilterCount > 0 ? "bg-brand-soft text-brand-accent-text" : "text-brand-muted"}`}>
          {selectedFilterCount}
        </span>
        <ChevronDown size={14} aria-hidden="true" className={filtersOpen ? "rotate-180" : ""} />
      </button>
      {/* Keep controls mounted so collapsing preserves selections and focus state. */}
      <div id={filtersId} className={`w-full space-y-3 lg:contents lg:space-y-0 ${filtersOpen ? "" : "hidden"}`}>
        <div className="flex flex-wrap items-center gap-2 lg:contents">
          <MultiSelectDropdown
            triggerClassName="h-10 text-sm"
            label="Сегмент"
            options={segments}
            selected={segmentFilters}
            onChange={setSegmentFilters}
            counts={segmentCounts}
          />

          <MultiSelectDropdown
            triggerClassName="h-10 text-sm"
            label="Город"
            options={cities}
            selected={cityFilters}
            onChange={setCityFilters}
            counts={cityCounts}
          />

          <MultiSelectDropdown
            triggerClassName="h-10 text-sm"
            label="Приоритет"
            options={PRIORITY_OPTIONS}
            selected={priorityFilters}
            onChange={setPriorityFilters}
            counts={priorityCounts}
          />

          <MultiSelectDropdown
            triggerClassName="h-10 text-sm"
            label="Tier"
            options={TIER_OPTIONS}
            selected={tierFilters}
            onChange={setTierFilters}
            counts={tierCounts}
          />

          {dealTypes.length > 0 && (
            <MultiSelectDropdown
              triggerClassName="h-10 text-sm"
              label="Тип сделки"
              options={dealTypes}
              selected={dealTypeFilters}
              onChange={setDealTypeFilters}
              counts={dealTypeCounts}
            />
          )}

          {sources.length > 0 && (
            <MultiSelectDropdown
              triggerClassName="h-10 text-sm"
              label="Источник"
              options={sources}
              selected={sourceFilters}
              onChange={setSourceFilters}
              counts={sourceCounts}
            />
          )}

          <select
            aria-label="Форма заявки"
            value={formId ?? ""}
            onChange={(e) => setFormId(e.target.value || undefined)}
            className="h-10 max-w-full sm:max-w-64 text-sm px-3 rounded-full bg-brand-bg border border-brand-border outline-none focus:border-brand-accent"
          >
            <option value="">Все источники</option>
            {forms
              .filter((f) => f.is_active)
              .map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
          </select>

        </div>
        <div className="flex w-full flex-wrap items-center gap-2">
          <button
            type="button"
            aria-pressed={needsReview === true}
            onClick={() => setNeedsReview((v) => (v === true ? undefined : true))}
            className={`inline-flex h-10 items-center whitespace-nowrap rounded-full border px-3 text-sm font-semibold transition-colors ${
              needsReview === true
                ? "bg-warning border-warning text-white"
                : "bg-brand-bg border border-brand-border text-brand-muted hover:border-warning"
            }`}
          >
            Только AI-созданные
          </button>

          {tags.length > 0 && (
            <MultiSelectDropdown
              triggerClassName="h-10 text-sm"
              label="Теги"
              options={tags}
              selected={tagFilters}
              onChange={setTagFilters}
              counts={tagCounts}
            />
          )}

          <span aria-hidden="true" className="hidden h-6 border-l border-brand-border sm:block" />

          <FitSlider value={fitMin} onChange={setFitMin} />

          <span aria-hidden="true" className="hidden h-6 border-l border-brand-border sm:block" />

          {/* Keep the two contact conditions together when rows wrap. */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setHasEmailOnly((v) => !v)}
              aria-pressed={hasEmailOnly}
              className={`inline-flex h-10 items-center gap-2 px-3 rounded-full text-sm font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
                hasEmailOnly
                  ? "bg-brand-soft text-brand-accent-text border-brand-accent/30"
                  : "bg-brand-bg text-brand-muted border-brand-border hover:border-brand-border"
              }`}
            >
              С email
            </button>
            <button
              type="button"
              onClick={() => setHasPhoneOnly((v) => !v)}
              aria-pressed={hasPhoneOnly}
              className={`inline-flex h-10 items-center gap-2 px-3 rounded-full text-sm font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
                hasPhoneOnly
                  ? "bg-brand-soft text-brand-accent-text border-brand-accent/30"
                  : "bg-brand-bg text-brand-muted border-brand-border hover:border-brand-border"
              }`}
            >
              С телефоном
            </button>
          </div>

          {activeFilterCount > 0 && (
            <>
              <span aria-hidden="true" className="hidden h-6 border-l border-brand-border sm:block" />
              <button
                type="button"
                onClick={resetAllFilters}
                className="inline-flex h-10 items-center gap-2 px-3 rounded-full text-sm font-semibold text-rose hover:bg-rose/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose focus-visible:ring-offset-1"
              >
                <X size={12} />
                Сбросить ({activeFilterCount})
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
