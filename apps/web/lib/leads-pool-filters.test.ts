/**
 * Сериализация выборки базы лидов (аудит G6).
 *
 * Одно состояние экрана превращается в параметры запроса и в тело для
 * экспорта и выдачи. Если хоть одно поле теряется по дороге, действие
 * начинает работать по другой выборке, чем список, — с этого G6 и начался.
 */
import { describe, expect, it } from "vitest";
import {
  activeFilterCount,
  EMPTY_POOL_FILTERS,
  poolFilterBody,
  poolQueryParams,
  poolScopeParams,
  type PoolFilterState,
} from "./leads-pool-filters";

const FULL: PoolFilterState = {
  cities: ["Москва", "Казань"],
  segments: ["Кофейни и кафе"],
  priorities: ["A", "B"],
  tiers: ["A"],
  dealTypes: ["station"],
  sources: ["outbound"],
  tags: ["vip", "2026"],
  fitMin: 42,
  search: "  Целевая  ",
  hasEmail: true,
  hasPhone: true,
  formId: "form-1",
  needsReview: false,
};

describe("poolQueryParams", () => {
  it("множественный выбор кодируется повторением параметра", () => {
    const p = poolQueryParams(FULL);
    expect(p.getAll("city")).toEqual(["Москва", "Казань"]);
    expect(p.getAll("priority")).toEqual(["A", "B"]);
    expect(p.getAll("tag")).toEqual(["vip", "2026"]);
    expect(p.toString()).toContain("city=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0");
  });

  it("каждый активный фильтр попадает в запрос", () => {
    const p = poolQueryParams(FULL);
    expect(p.getAll("segment")).toEqual(["Кофейни и кафе"]);
    expect(p.getAll("tier")).toEqual(["A"]);
    expect(p.getAll("deal_type")).toEqual(["station"]);
    expect(p.getAll("source")).toEqual(["outbound"]);
    expect(p.get("fit_min")).toBe("42");
    expect(p.get("has_email")).toBe("true");
    expect(p.get("has_phone")).toBe("true");
    expect(p.get("form_id")).toBe("form-1");
    expect(p.get("needs_review")).toBe("false");
  });

  it("поиск обрезается по краям", () => {
    expect(poolQueryParams(FULL).get("q")).toBe("Целевая");
  });

  it("пробельный поиск — это отсутствие поиска", () => {
    const p = poolQueryParams({ ...EMPTY_POOL_FILTERS, search: "   " });
    expect(p.has("q")).toBe(false);
  });

  it("пустое состояние не отправляет ничего", () => {
    expect(poolQueryParams(EMPTY_POOL_FILTERS).toString()).toBe("");
  });
});

describe("poolFilterBody", () => {
  it("несёт те же поля, что и параметры запроса", () => {
    expect(poolFilterBody(FULL)).toEqual({
      assignment_status: "pool",
      cities: ["Москва", "Казань"],
      segments: ["Кофейни и кафе"],
      priorities: ["A", "B"],
      tiers: ["A"],
      deal_types: ["station"],
      sources: ["outbound"],
      tags: ["vip", "2026"],
      fit_min: 42,
      q: "Целевая",
      has_email: true,
      has_phone: true,
      form_id: "form-1",
      needs_review: false,
    });
  });

  it("ни одно активное поле не теряется относительно запроса списка", () => {
    // Тело и параметры описывают одну выборку. Проверяем это по именам:
    // множественные — во множественном числе, остальные один в один.
    const params = poolQueryParams(FULL);
    const body = poolFilterBody(FULL) as Record<string, unknown>;
    const pairs: [string, string][] = [
      ["city", "cities"],
      ["segment", "segments"],
      ["priority", "priorities"],
      ["tier", "tiers"],
      ["deal_type", "deal_types"],
      ["source", "sources"],
      ["tag", "tags"],
    ];
    for (const [param, key] of pairs) {
      expect(body[key]).toEqual(params.getAll(param));
    }
    for (const key of ["fit_min", "q", "form_id"]) {
      expect(String(body[key])).toBe(params.get(key));
    }
  });

  it("пустое состояние сужает выборку только до пула", () => {
    expect(poolFilterBody(EMPTY_POOL_FILTERS)).toEqual({
      assignment_status: "pool",
    });
  });
});

describe("poolScopeParams", () => {
  it("несёт только то, от чего зависят счётчики фасетов", () => {
    const p = poolScopeParams(FULL);
    expect(p.get("form_id")).toBe("form-1");
    expect(p.get("needs_review")).toBe("false");
    // Иначе каждый невыбранный фасет показывал бы ноль.
    expect(p.has("city")).toBe(false);
    expect(p.has("q")).toBe(false);
  });
});

describe("activeFilterCount", () => {
  it("считает каждое активное условие один раз", () => {
    expect(activeFilterCount(EMPTY_POOL_FILTERS)).toBe(0);
    expect(activeFilterCount(FULL)).toBe(13);
    expect(
      activeFilterCount({ ...EMPTY_POOL_FILTERS, search: "   " }),
    ).toBe(0);
  });
});
