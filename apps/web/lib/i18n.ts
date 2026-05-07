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
