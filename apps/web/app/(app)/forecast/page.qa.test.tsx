/**
 * QA additions (sonnet-qa, FORECAST-01 verification pass).
 *
 * Covers three checks not exercised by the implementer's page.test.tsx:
 *  1. an aggregate error must surface an explicit error, never "0 ₽";
 *  2. loading state must not present stale/previous values as current;
 *  3. no request anywhere on this page asks for `page_size` (the metric
 *     path must never again depend on how many list rows fit a page).
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: { ...actual.api, get: apiGet } };
});

vi.mock("@/lib/hooks/use-utm-stats", () => ({
  useUtmStats: () => ({ data: [], isLoading: false }),
}));
vi.mock("@/lib/hooks/use-stage-dwell", () => ({
  useStageDwell: () => ({ data: [], isLoading: false }),
}));

import ForecastPage from "./page";

const SUMMARY = {
  pipeline_total: 1_919_400,
  weighted_total: 480_000,
  at_risk_total: 250_000,
  won_recent: 700_000,
  stage_bars: [{ stage_id: "s1", name: "Квалификация", total: 1_919_400, count: 1200 }],
  at_risk_deals: [
    {
      id: "l1",
      company_name: "Альфа Ритейл",
      amount: 250_000,
      overdue_days: 4,
      stage_name: "Квалификация",
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ForecastPage />
    </QueryClientProvider>,
  );
  return queryClient;
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  apiGet.mockReset();
});

describe("ForecastPage — QA additions", () => {
  it("ошибка агрегата: KPI-числа не рендерятся вообще, включая «0 ₽»", async () => {
    apiGet.mockRejectedValue(new Error("boom"));
    renderPage();

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
    // Ни один узел KPI (Воронка/Взвешенный прогноз/Под угрозой/Закрыто) не
    // должен присутствовать после ошибки — страница прячет весь блок
    // сумм, а не подставляет нули под теми же подписями.
    expect(screen.queryByText("Воронка")).toBeNull();
    expect(screen.queryByText("Взвешенный прогноз")).toBeNull();
    expect(screen.queryByText("0 ₽")).toBeNull();
    expect(screen.queryByText(/млн ₽|тыс ₽/)).toBeNull();
  });

  it("во время загрузки не показывает предыдущие значения как актуальные", async () => {
    const first = deferred<typeof SUMMARY>();
    apiGet.mockReturnValueOnce(first.promise);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ForecastPage />
      </QueryClientProvider>,
    );

    // While the request is in flight, the real total must not be visible
    // yet -- only the loading skeleton (no numeric KPI text at all).
    expect(screen.queryByText("1.9 млн ₽")).toBeNull();
    expect(screen.queryByText("0 ₽")).toBeNull();

    first.resolve(SUMMARY);
    expect(await screen.findByText("1.9 млн ₽")).toBeInTheDocument();

    // Now trigger a refetch that will fail — the previously-fetched
    // 1.9 млн ₽ must not linger on screen presented as the current value
    // once the page acts on the error (isError flips true and the KPI
    // block is replaced by the failure message, not the old number).
    apiGet.mockRejectedValueOnce(new Error("refetch failed"));
    await queryClient.refetchQueries({ queryKey: ["forecast"] });

    await waitFor(() => {
      expect(screen.getAllByText("Не удалось загрузить прогноз").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("1.9 млн ₽")).toBeNull();
  });

  it("ни один запрос на странице не использует page_size (метрики не зависят от объёма страницы списка)", async () => {
    apiGet.mockResolvedValue(SUMMARY);
    renderPage();

    await screen.findByText("1.9 млн ₽");

    const urls = apiGet.mock.calls.map((c) => String(c[0]));
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((u) => !u.includes("page_size"))).toBe(true);
    expect(urls.every((u) => !u.startsWith("/leads?"))).toBe(true);
    expect(urls).toEqual(["/leads/forecast"]);
  });
});
