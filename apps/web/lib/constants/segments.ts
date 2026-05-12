// Sprint 3.5 — canonical segment vocabulary. ADR-023.
// Mirrors apps/api/app/leads/constants.py:SEGMENT_CHOICES — both files
// must stay in sync. Adding a key is a code change in both halves +
// a one-row data backfill, not a DB migration.

export const SEGMENT_CHOICES = [
  { key: "food_retail",     label: "Продуктовый ритейл" },
  { key: "non_food_retail", label: "Непродуктовый ритейл" },
  { key: "coffee_shops",    label: "Кофейни / Кафе / Рестораны" },
  { key: "qsr_fast_food",   label: "QSR / Fast Food" },
  { key: "gas_stations",    label: "АЗС" },
  { key: "office",          label: "Офисы" },
  { key: "hotel",           label: "Отели" },
  { key: "distributor",     label: "Дистрибьюторы" },
] as const;

export type SegmentKey = (typeof SEGMENT_CHOICES)[number]["key"];

export const SEGMENT_LABELS: Record<string, string> = Object.fromEntries(
  SEGMENT_CHOICES.map((s) => [s.key, s.label])
);

export function segmentLabel(s: string | null | undefined): string {
  if (!s) return "";
  return SEGMENT_LABELS[s] ?? s;
}
