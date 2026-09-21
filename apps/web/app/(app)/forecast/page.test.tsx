/**
 * FC-04: прогноз берёт суммы с сервера и честно показывает ошибку.
 *
 * До правки страница складывала одну страницу `GET /leads`, прося 500 строк
 * при потолке роута 200: запрос отбивался валидацией, а суммы через `?? 0`
 * показывали нули — «сделок нет» вместо «данные не загрузились».
 */
import { render, screen } from "@testing-library/react";
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
}

afterEach(() => {
  apiGet.mockReset();
});

describe("ForecastPage", () => {
  it("берёт суммы серверным агрегатом, а не страницей списка лидов", async () => {
    apiGet.mockResolvedValue(SUMMARY);
    renderPage();

    expect(await screen.findByText("1.9 млн ₽")).toBeInTheDocument();
    expect(screen.getByText("Альфа Ритейл")).toBeInTheDocument();

    const urls = apiGet.mock.calls.map((c) => String(c[0]));
    expect(urls).toContain("/leads/forecast");
    expect(urls.every((u) => !u.includes("page_size"))).toBe(true);
  });

  it("при ошибке запроса показывает ошибку, а не нули", async () => {
    apiGet.mockRejectedValue(new Error("boom"));
    renderPage();

    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
    expect(screen.getAllByText("Не удалось загрузить прогноз").length).toBeGreaterThan(0);
    expect(screen.queryByText("0 ₽")).toBeNull();
  });
});
