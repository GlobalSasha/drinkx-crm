// Shared label maps for Russian-friendly display of backend slugs.
// Add new entries here; components import from this module, not define locally.

// Canonical Russian segment values (also stored verbatim in the DB).
// Order is used by dropdown filters.
export const SEGMENT_OPTIONS = [
  "Продуктовый ритейл",
  "Непродуктовый ритейл",
  "Кофейни и кафе",
  "QSR / Fast Food",
  "HORECA",
  "АЗС",
  "Дистрибьюторы оборудования",
  "Зерно обжарка экстракт",
  "Вендинг",
  "Другое",
] as const;

export const SEGMENT_LABELS: Record<string, string> = Object.fromEntries(
  SEGMENT_OPTIONS.map((s) => [s, s]),
);

export function segmentLabel(s: string): string {
  return SEGMENT_LABELS[s] ?? s;
}

export const DEAL_TYPE_LABELS: Record<string, string> = {
  enterprise_direct:   "Enterprise",
  qsr:                 "QSR",
  distributor_partner: "Дистрибьютор",
  raw_materials:       "Сырьё",
  private_small:       "Малый бизнес",
  service_repeat:      "Сервис",
};

export function dealTypeLabel(s: string | null | undefined): string {
  if (!s) return "";
  return DEAL_TYPE_LABELS[s] ?? s;
}

export const PRIORITY_LABELS: Record<string, string> = {
  A: "Приоритет A",
  B: "Приоритет B",
  C: "Приоритет C",
  D: "Приоритет D",
};

export function priorityLabel(p: string | null | undefined): string {
  if (!p) return "";
  return PRIORITY_LABELS[p] ?? `Приоритет ${p}`;
}
