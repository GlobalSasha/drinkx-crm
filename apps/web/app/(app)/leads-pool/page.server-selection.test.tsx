/**
 * База лидов ведётся сервером (аудит G6).
 *
 * Здесь работают настоящие хуки, подменён только HTTP. Проверяется то,
 * чего не было до G6: каждое условие уходит в запрос, страницы берутся с
 * сервера, счётчики фильтров приходят из метаданных, смена условия
 * возвращает на первую страницу, а поиск не перебирает загруженные строки.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: { ...actual.api, get: apiGet, post: apiPost } };
});

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => ({ data: { id: "me-1", role: "head" }, isLoading: false }),
}));
vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({ data: { items: [], total: 0 } }),
}));
vi.mock("@/lib/hooks/use-forms", () => ({
  useForms: () => ({ data: { items: [] } }),
}));

import LeadsPoolPage from "./page";

const FACETS = {
  cities: [
    { value: "Москва", count: 900 },
    { value: "Казань", count: 300 },
  ],
  segments: [{ value: "Кофейни и кафе", count: 700 }],
  priorities: [
    { value: "A", count: 1 },
    { value: "B", count: 1199 },
  ],
  tiers: [
    { value: "A", count: 1 },
    { value: "C", count: 1199 },
  ],
  deal_types: [{ value: "station", count: 42 }],
  sources: [{ value: "outbound", count: 7 }],
  tags: [{ value: "vip", count: 120 }],
  total: 1200,
};

function lead(id: string, name: string) {
  return {
    id,
    company_name: name,
    city: "Москва",
    segment: "Ритейл",
    email: null,
    phone: null,
    inn: null,
    source: null,
    tags_json: [],
    deal_type: null,
    priority: "B",
    score: 50,
    fit_score: 50,
    assignment_status: "pool",
    assigned_to: null,
    needs_review: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

/** Все запросы списка, что ушли на сервер, в порядке отправки. */
function listCalls(): URL[] {
  return apiGet.mock.calls
    .map(([u]) => u as string)
    .filter((u) => u.startsWith("/leads/pool?"))
    .map((u) => new URL(u, "http://test"));
}

function lastList(): URL {
  const calls = listCalls();
  return calls[calls.length - 1];
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <LeadsPoolPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useRealTimers();
  apiGet.mockReset().mockImplementation((url: string) => {
    if (url.startsWith("/leads/pool/facets")) return Promise.resolve(FACETS);
    if (url.startsWith("/leads/pool")) {
      const page = Number(new URL(url, "http://test").searchParams.get("page") ?? 1);
      return Promise.resolve({
        items: [lead(`lead-p${page}`, `Компания страница ${page}`)],
        total: 1200,
        page,
        page_size: 50,
      });
    }
    return Promise.resolve({ items: [], total: 0 });
  });
  apiPost.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("База лидов — выборку определяет сервер", () => {
  it("первый запрос — страница, а не весь пул", async () => {
    renderPage();
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(0));

    const url = lastList();
    expect(url.searchParams.get("page")).toBe("1");
    expect(Number(url.searchParams.get("page_size"))).toBeLessThanOrEqual(200);
    expect(url.searchParams.get("page_size")).not.toBe("500");
  });

  it("счётчики в фильтрах приходят из метаданных, а не из строк", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Компания страница 1/)).toBeInTheDocument());

    // На странице ровно одна карточка, а в фильтре «Приоритет» рядом с «B»
    // стоит 1199 — это число с сервера, из строк его взять неоткуда.
    await userEvent.click(screen.getByRole("button", { name: /Приоритет/ }));
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByText("1199")).toBeInTheDocument();
  });

  it("общее число — серверное, а не длина загруженного", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/из 1200/).length).toBeGreaterThan(0));
    // Строк на странице одна, а число — по всей выборке на сервере.
    expect(screen.getAllByText(/Компания страница 1/)).toHaveLength(1);
  });

  it("выбор фильтра уходит на сервер и возвращает на первую страницу", async () => {
    renderPage();
    await screen.findByRole("button", { name: "Вперёд" });

    // Уходим на вторую страницу…
    await userEvent.click(screen.getByRole("button", { name: "Вперёд" }));
    await waitFor(() => expect(lastList().searchParams.get("page")).toBe("2"));

    // …и меняем фильтр: страница обязана сброситься.
    await userEvent.click(screen.getByRole("button", { name: /^Город/ }));
    const listbox = await screen.findByRole("listbox");
    await userEvent.click(within(listbox).getByText("Казань"));

    await waitFor(() => {
      const url = lastList();
      expect(url.searchParams.getAll("city")).toEqual(["Казань"]);
      expect(url.searchParams.get("page")).toBe("1");
    });
  });

  it("листание запрашивает у сервера именно ту страницу", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Компания страница 1/)).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Вперёд" }));
    await waitFor(() => expect(screen.getByText(/Компания страница 2/)).toBeInTheDocument());
    expect(lastList().searchParams.get("page")).toBe("2");
  });

  it("поиск уходит на сервер, с задержкой и один раз", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(0));
    const before = listCalls().length;

    await user.type(screen.getByPlaceholderText(/Поиск/), "Целевая");
    // Пока идёт набор, запросов на каждый символ быть не должно.
    expect(listCalls().length).toBe(before);

    vi.advanceTimersByTime(400);
    await waitFor(() => expect(lastList().searchParams.get("q")).toBe("Целевая"));
    // Один запрос на весь набранный текст, а не семь.
    expect(listCalls().length).toBe(before + 1);
  });

  it("пустой ответ сервера — это «ничего не найдено», а не пустая база", async () => {
    apiGet.mockImplementation((url: string) => {
      if (url.startsWith("/leads/pool/facets")) return Promise.resolve(FACETS);
      return Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 });
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("В пуле пока пусто")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /^Город/ }));
    const listbox = await screen.findByRole("listbox");
    await userEvent.click(within(listbox).getByText("Казань"));

    await waitFor(() => expect(screen.getByText("Ничего не найдено")).toBeInTheDocument());
  });
});

describe("старая схема не должна вернуться", () => {
  const pageSource = readFileSync(path.join(__dirname, "page.tsx"), "utf8");
  const hookSource = readFileSync(
    path.join(__dirname, "..", "..", "..", "lib", "hooks", "use-leads.ts"),
    "utf8",
  );

  it("страница не просит весь пул одним запросом", () => {
    // Комментарии объясняют, как было, и не должны валить проверку —
    // смотрим только на код.
    const code = (src: string) =>
      src
        .split("\n")
        .filter((line) => {
          const s = line.trim();
          return !s.startsWith("//") && !s.startsWith("*") && !s.startsWith("/*");
        })
        .join("\n");
    for (const source of [pageSource, hookSource]) {
      expect(code(source)).not.toMatch(/page_size[^\n]{0,12}500/);
    }
  });

  it("страница не решает принадлежность к выборке у себя", () => {
    // `filter(...)` по строкам пула — это и есть тот дефект: он
    // возвращается вместе с фразами вроде `allItems.filter` или
    // `items.filter((l) => ...)`.
    expect(pageSource).not.toMatch(/allItems/);
    expect(pageSource).not.toMatch(/\.items\s*\)?\s*\.filter\(/);
    expect(pageSource).not.toMatch(/tierFromScore\s*\(/);
  });

  it("экспорт получает то же описание выборки, что и список", () => {
    expect(pageSource).toContain("poolFilterBody(filters)");
    // Прежняя сборка отправляла город и сегмент только когда выбран один.
    expect(pageSource).not.toMatch(/cityFilters\.length === 1/);
  });
});
