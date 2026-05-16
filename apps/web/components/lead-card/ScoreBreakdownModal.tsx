"use client";

// Editable per-criterion scoring popup — Sprint Lead Card v2.
//
// Manager clicks dots 0..max_value on each row; total + priority pill
// update LIVE in the modal header before save. Backend mirrors the
// formula in `app.leads.scoring.compute_total`, so the saved values
// produce the same total the user previewed.

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import {
  useScoreBreakdown,
  useUpdateScoreDetails,
} from "@/lib/hooks/use-lead-v2";

interface Props {
  leadId: string;
  onClose: () => void;
}

// Mirrors `priority_from_score` + `priority_label` on the backend.
const PRIORITY_TABLE: Array<[number, string, string, string]> = [
  // [threshold, letter, label, pill-color-class]
  [80, "A", "Стратегический", "bg-success/15 text-success"],
  [60, "B", "Перспективный", "bg-success/10 text-success"],
  [40, "C", "Низкий", "bg-warning/10 text-warning"],
  [0, "D", "Архив", "bg-black/5 text-brand-muted"],
];

function priorityFromScore(total: number): {
  letter: string;
  label: string;
  pill: string;
} {
  for (const [threshold, letter, label, pill] of PRIORITY_TABLE) {
    if (total >= threshold) return { letter, label, pill };
  }
  return { letter: "D", label: "Архив", pill: "bg-black/5 text-brand-muted" };
}

export function ScoreBreakdownModal({ leadId, onClose }: Props) {
  const { data, isLoading, isError } = useScoreBreakdown(leadId, true);
  const update = useUpdateScoreDetails(leadId);

  // Local edit state keyed on criterion `key`. Seeded from `current_value`
  // when the breakdown loads; resets if the modal is reopened.
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    if (data && !seeded) {
      const seed: Record<string, number> = {};
      for (const c of data.criteria) seed[c.key] = c.current_value;
      setDraft(seed);
      setSeeded(true);
    }
  }, [data, seeded]);

  // Live total computed from the draft (mirrors backend formula).
  const liveTotal = useMemo(() => {
    if (!data) return 0;
    let total = 0;
    for (const c of data.criteria) {
      if (c.max_value <= 0) continue;
      const v = Math.max(0, Math.min(c.max_value, draft[c.key] ?? 0));
      total += (v / c.max_value) * c.weight;
    }
    return Math.round(total);
  }, [data, draft]);

  const livePriority = priorityFromScore(liveTotal);
  const isDirty = useMemo(() => {
    if (!data) return false;
    return data.criteria.some((c) => (draft[c.key] ?? 0) !== c.current_value);
  }, [data, draft]);

  function setValue(key: string, value: number) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleSave() {
    update.mutate(draft, { onSuccess: () => onClose() });
  }

  return (
    <Modal open onClose={onClose} title="Из чего собран балл" size="max-w-3xl">
      <div className="-m-6">
        <header className="px-6 py-4 border-b border-brand-border flex items-center justify-between gap-3 flex-wrap">
          <h3 className="type-card-title text-brand-primary">
            Из чего собран балл
          </h3>
          <div className="flex items-center gap-2">
            <span className="type-body font-mono tabular-nums text-brand-primary">
              {liveTotal} / {data?.max ?? 100}
            </span>
            <span
              className={`type-caption font-semibold px-2.5 py-0.5 rounded-full ${livePriority.pill}`}
            >
              {livePriority.label}
            </span>
          </div>
        </header>

        <div className="px-6 py-5 max-h-[60vh] overflow-y-auto">
          {isLoading && (
            <div className="flex items-center gap-2 type-caption text-brand-muted">
              <Loader2 size={13} className="animate-spin" />
              Загрузка критериев…
            </div>
          )}
          {isError && (
            <p className="type-caption text-rose">
              Не удалось загрузить детализацию
            </p>
          )}
          {data && data.criteria.length === 0 && (
            <p className="type-hint text-brand-muted">
              Детализация скоринга пока недоступна для этого лида.
            </p>
          )}
          {data && data.criteria.length > 0 && (
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {data.criteria.map((c) => {
                const v = draft[c.key] ?? 0;
                const pct = c.max_value > 0 ? v / c.max_value : 0;
                const barColor = pct >= 0.6 ? "bg-success" : "bg-warning";
                return (
                  <li key={c.key} className="space-y-1.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="type-caption font-semibold text-brand-primary">
                        {c.label}
                      </span>
                      <span className="font-mono type-caption text-brand-muted tabular-nums">
                        {v} / {c.max_value}
                        <span className="ml-1.5 bg-brand-panel px-1.5 py-0.5 rounded-md">
                          ×{c.weight}%
                        </span>
                      </span>
                    </div>
                    <DotPicker
                      value={v}
                      max={c.max_value}
                      onChange={(next) => setValue(c.key, next)}
                    />
                    <div className="h-1 bg-brand-panel rounded-full overflow-hidden">
                      <div
                        className={`h-full ${barColor} transition-all duration-200`}
                        style={{ width: `${pct * 100}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <footer className="px-6 py-3 border-t border-brand-border flex items-center justify-between gap-3 flex-wrap">
          <p className="type-hint text-brand-muted max-w-md">
            Веса критериев настраиваются в Settings → Скоринг. Балл
            пересчитывается автоматически при сохранении.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={update.isPending}
              className="px-4 py-1.5 type-caption font-semibold text-brand-muted hover:text-brand-primary disabled:opacity-40"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={update.isPending || !isDirty}
              className="inline-flex items-center gap-1 px-4 py-1.5 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2"
            >
              {update.isPending && <Loader2 size={11} className="animate-spin" />}
              Сохранить
            </button>
          </div>
        </footer>
      </div>
    </Modal>
  );
}

function DotPicker({
  value,
  max,
  onChange,
}: {
  value: number;
  max: number;
  onChange: (v: number) => void;
}) {
  // Render `max + 1` dots representing 0..max. Click sets the value.
  return (
    <div className="flex items-center gap-1.5" role="group" aria-label="Оценка">
      {Array.from({ length: max + 1 }, (_, i) => {
        const active = i <= value;
        return (
          <button
            key={i}
            type="button"
            onClick={() => onChange(i)}
            aria-label={`Поставить ${i}`}
            aria-pressed={active}
            className={`w-5 h-5 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
              active
                ? "bg-brand-accent"
                : "bg-brand-panel hover:bg-brand-soft"
            }`}
          />
        );
      })}
    </div>
  );
}
