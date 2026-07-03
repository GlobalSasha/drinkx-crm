"use client";

import { Search, X } from "lucide-react";
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
  resetAllFilters: () => void;
}

// ---- Filter row — flex-wraps over 1-2 lines depending on viewport.
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
  resetAllFilters,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 mt-3">
      {/* Search — name + email + phone + INN. */}
      <div className="relative">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted pointer-events-none"
        />
        <input
          type="text"
          placeholder="Поиск: имя, email, телефон, ИНН"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8 pr-3 py-1.5 text-sm bg-brand-bg border border-brand-border rounded-full outline-none focus:border-brand-accent/40 focus:bg-white transition duration-300 w-full sm:w-64"
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

      <select
        value={formId ?? ""}
        onChange={(e) => setFormId(e.target.value || undefined)}
        className="text-sm px-2 py-1.5 rounded-lg bg-brand-bg border border-brand-border outline-none focus:border-brand-accent"
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

      <button
        type="button"
        onClick={() => setNeedsReview((v) => (v === true ? undefined : true))}
        className={`text-xs px-2 py-1 rounded ${
          needsReview === true
            ? "bg-warning text-white"
            : "bg-brand-bg border border-brand-border text-brand-muted hover:border-warning"
        }`}
      >
        Только AI-созданные
      </button>

      {tags.length > 0 && (
        <MultiSelectDropdown
          label="Теги"
          options={tags}
          selected={tagFilters}
          onChange={setTagFilters}
          counts={tagCounts}
        />
      )}

      <span className="text-brand-muted text-xs">|</span>

      <FitSlider value={fitMin} onChange={setFitMin} />

      <span className="text-brand-muted text-xs">|</span>

      {/* Boolean toggles — render as pill buttons with checked state. */}
      <button
        type="button"
        onClick={() => setHasEmailOnly((v) => !v)}
        aria-pressed={hasEmailOnly}
        className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
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
        className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
          hasPhoneOnly
            ? "bg-brand-soft text-brand-accent-text border-brand-accent/30"
            : "bg-brand-bg text-brand-muted border-brand-border hover:border-brand-border"
        }`}
      >
        С телефоном
      </button>

      {activeFilterCount > 0 && (
        <>
          <span className="text-brand-muted text-xs">|</span>
          <button
            type="button"
            onClick={resetAllFilters}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-semibold text-rose hover:bg-rose/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose focus-visible:ring-offset-1"
          >
            <X size={12} />
            Сбросить ({activeFilterCount})
          </button>
        </>
      )}
    </div>
  );
}
