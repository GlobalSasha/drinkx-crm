/**
 * Одно описание выборки базы лидов на клиенте (аудит G6).
 *
 * До G6 состояние фильтров жило только в компоненте страницы, а решение
 * «подходит ли лид» принимал `Array.filter` по первым 500 загруженным
 * строкам. Поэтому список, счётчики, экспорт и «Выдать по фильтру»
 * работали каждый по своему набору условий, и карточка за границей
 * страницы не находилась ничем.
 *
 * Здесь — единственное место, где состояние экрана превращается в то,
 * что уходит на сервер. Повторять здесь сам алгоритм отбора нельзя: он
 * живёт в `app/leads/selection.py`, и второй реализации быть не должно.
 */

import type { LeadSelectionBody } from "@/lib/types";

/** Состояние фильтров экрана. Ровно то, что человек выбрал. */
export interface PoolFilterState {
  cities: string[];
  segments: string[];
  priorities: string[];
  tiers: string[];
  dealTypes: string[];
  sources: string[];
  tags: string[];
  fitMin: number;
  search: string;
  hasEmail: boolean;
  hasPhone: boolean;
  formId?: string;
  needsReview?: boolean;
}

export const EMPTY_POOL_FILTERS: PoolFilterState = {
  cities: [],
  segments: [],
  priorities: [],
  tiers: [],
  dealTypes: [],
  sources: [],
  tags: [],
  fitMin: 0,
  search: "",
  hasEmail: false,
  hasPhone: false,
  formId: undefined,
  needsReview: undefined,
};

/** Сколько фильтров активно — для подписи «Сбросить (N)». */
export function activeFilterCount(f: PoolFilterState): number {
  return (
    (f.cities.length > 0 ? 1 : 0) +
    (f.segments.length > 0 ? 1 : 0) +
    (f.priorities.length > 0 ? 1 : 0) +
    (f.tiers.length > 0 ? 1 : 0) +
    (f.dealTypes.length > 0 ? 1 : 0) +
    (f.sources.length > 0 ? 1 : 0) +
    (f.tags.length > 0 ? 1 : 0) +
    (f.fitMin > 0 ? 1 : 0) +
    (f.search.trim() ? 1 : 0) +
    (f.hasEmail ? 1 : 0) +
    (f.hasPhone ? 1 : 0) +
    (f.formId ? 1 : 0) +
    (f.needsReview !== undefined ? 1 : 0)
  );
}

/**
 * Параметры запроса. Множественный выбор — повторением параметра:
 * `?city=Москва&city=Казань`. Та же кодировка и у списка, и у счётчиков.
 */
export function poolQueryParams(f: PoolFilterState): URLSearchParams {
  const p = new URLSearchParams();
  const multi = (name: string, values: string[]) => {
    for (const v of values) if (v) p.append(name, v);
  };
  multi("city", f.cities);
  multi("segment", f.segments);
  multi("priority", f.priorities);
  multi("tier", f.tiers);
  multi("deal_type", f.dealTypes);
  multi("source", f.sources);
  multi("tag", f.tags);
  if (f.fitMin > 0) p.set("fit_min", String(f.fitMin));
  const q = f.search.trim();
  if (q) p.set("q", q);
  if (f.hasEmail) p.set("has_email", "true");
  if (f.hasPhone) p.set("has_phone", "true");
  if (f.formId) p.set("form_id", f.formId);
  if (f.needsReview !== undefined) p.set("needs_review", String(f.needsReview));
  return p;
}

/**
 * То же описание в теле запроса — для экспорта и для «Выдать по фильтру».
 * Бэкенд читает его тем же `LeadSelection.from_json`, что и параметры
 * запроса: ни одно поле по дороге не теряется.
 *
 * Пустые значения не отправляются: пустой список — это отсутствие фильтра,
 * а не «поле равно пустоте».
 */
export function poolFilterBody(f: PoolFilterState): LeadSelectionBody {
  const body: LeadSelectionBody = { assignment_status: "pool" };
  if (f.cities.length) body.cities = f.cities;
  if (f.segments.length) body.segments = f.segments;
  if (f.priorities.length) body.priorities = f.priorities;
  if (f.tiers.length) body.tiers = f.tiers;
  if (f.dealTypes.length) body.deal_types = f.dealTypes;
  if (f.sources.length) body.sources = f.sources;
  if (f.tags.length) body.tags = f.tags;
  if (f.fitMin > 0) body.fit_min = f.fitMin;
  const q = f.search.trim();
  if (q) body.q = q;
  if (f.hasEmail) body.has_email = true;
  if (f.hasPhone) body.has_phone = true;
  if (f.formId) body.form_id = f.formId;
  if (f.needsReview !== undefined) body.needs_review = f.needsReview;
  return body;
}

/**
 * Область пула: только то, от чего зависят счётчики фасетов. Форма и
 * «требует проверки» задают границы базы, остальные фильтры на числа в
 * выпадающих списках не влияют — так это работало и до G6.
 */
export function poolScopeParams(f: PoolFilterState): URLSearchParams {
  const p = new URLSearchParams();
  if (f.formId) p.set("form_id", f.formId);
  if (f.needsReview !== undefined) p.set("needs_review", String(f.needsReview));
  return p;
}
