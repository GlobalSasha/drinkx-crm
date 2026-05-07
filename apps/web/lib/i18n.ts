// Shared label maps for Russian-friendly display of backend slugs.
// Add new entries here; components import from this module, not define locally.

export const SEGMENT_LABELS: Record<string, string> = {
  food_retail: "Продуктовый ритейл",
  non_food_retail: "Непродуктовый ритейл",
  coffee_shops: "Кофейни и кафе",
  qsr_fast_food: "QSR / Fast Food",
  gas_stations: "АЗС",
  coffee_equipment_distributors: "Дистрибьюторы оборудования",
  horeca: "HoReCa",
  restaurants: "Рестораны",
  hotels: "Отели",
};

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
