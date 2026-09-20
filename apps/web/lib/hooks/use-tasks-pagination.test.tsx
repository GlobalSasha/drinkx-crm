/**
 * Страница «Задачи»: отбор по статусу уходит на сервер, страницы берутся
 * курсором (аудит G5).
 *
 * До правки `/tasks` вызывался одним запросом с лимитом до 500 строк, а чипы
 * «открытые / закрытые / просроченные» фильтровали то, что приехало. На
 * большем числе задач нужная строка в ответ не попадала, и никакой фильтр её
 * уже не возвращал.
 */
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import type { MyTaskOut, TaskListOut } from "@/lib/types";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: { ...actual.api, get: apiGet } };
});

import { useTasks, TASKS_PAGE } from "./use-tasks";

const CURSOR = "0|2026-02-02T10:00:00+00:00|22222222-2222-2222-2222-222222222222";

function task(id: string): MyTaskOut {
  return {
    id,
    lead_id: null,
    lead_company_name: null,
    text: `Задача ${id}`,
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-02-01T00:00:00Z",
    assignee_user_id: "u1",
    assignee_name: "Кирилл",
    explicit_assignee_user_id: "u1",
    author_user_id: "u1",
    author_name: "Кирилл",
  };
}

const COUNTS = { total: 120, open: 90, done: 30, overdue: 7 };

const page1: TaskListOut = {
  items: [task("a"), task("b")],
  next_cursor: CURSOR,
  counts: COUNTS,
};
const page2: TaskListOut = { items: [task("c")], next_cursor: null, counts: COUNTS };

function wrap(qc: QueryClient) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = "TestQueryWrapper";
  return Wrapper;
}
const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

beforeEach(() => {
  apiGet.mockReset().mockImplementation((url: string) =>
    Promise.resolve(url.includes("cursor=") ? page2 : page1),
  );
});

describe("useTasks", () => {
  it("передаёт статус и размер страницы серверу", async () => {
    const { result } = renderHook(() => useTasks({ status: "overdue" }), {
      wrapper: wrap(client()),
    });
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    const url = apiGet.mock.calls[0][0] as string;
    expect(url).toContain("status=overdue");
    expect(url).toContain(`limit=${TASKS_PAGE}`);
  });

  it("status=all не уходит в запрос — это отсутствие фильтра", async () => {
    const { result } = renderHook(() => useTasks({ status: "all" }), {
      wrapper: wrap(client()),
    });
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(apiGet.mock.calls[0][0] as string).not.toContain("status=");
  });

  it("склеивает страницы и держит счётчики по всей выборке", async () => {
    const { result } = renderHook(() => useTasks({ status: "open" }), {
      wrapper: wrap(client()),
    });
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(result.current.counts).toEqual(COUNTS);

    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.items).toHaveLength(3));

    expect(apiGet.mock.calls[1][0] as string).toContain(
      `cursor=${encodeURIComponent(CURSOR)}`,
    );
    expect(result.current.hasNextPage).toBe(false);
    // Счётчик не съезжает к числу загруженных строк.
    expect(result.current.counts?.total).toBe(120);
  });

  it("поиск и границы срока уходят в запрос параметрами", async () => {
    const { result } = renderHook(
      () =>
        useTasks({
          status: "open",
          q: "Уникальный-маркер",
          dueFrom: "2026-02-01T00:00:00.000Z",
          dueTo: "2026-02-02T00:00:00.000Z",
        }),
      { wrapper: wrap(client()) },
    );
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    const url = apiGet.mock.calls[0][0] as string;
    expect(url).toContain(`q=${encodeURIComponent("Уникальный-маркер")}`);
    expect(url).toContain(`due_from=${encodeURIComponent("2026-02-01T00:00:00.000Z")}`);
    expect(url).toContain(`due_to=${encodeURIComponent("2026-02-02T00:00:00.000Z")}`);
  });

  it("смена поиска сбрасывает листание: новый запрос идёт без курсора", async () => {
    const qc = client();
    type Props = { q: string };
    const { rerender, result } = renderHook(({ q }: Props) => useTasks({ status: "open", q }), {
      wrapper: wrap(qc),
      initialProps: { q: "альфа" } as Props,
    });
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.items).toHaveLength(3));

    rerender({ q: "бета" });
    await waitFor(() => expect(apiGet.mock.calls.length).toBe(3));

    const url = apiGet.mock.calls[2][0] as string;
    expect(url).toContain("q=%D0%B1%D0%B5%D1%82%D0%B0");
    expect(url).not.toContain("cursor=");
    // Страница, взятая под старым поиском, не подмешивается к новому.
    await waitFor(() => expect(result.current.items).toHaveLength(2));
  });

  it("смена статуса — это новый запрос, а не фильтрация загруженного", async () => {
    const qc = client();
    type Props = { status: "open" | "done" };
    const { rerender, result } = renderHook(
      ({ status }: Props) => useTasks({ status }),
      { wrapper: wrap(qc), initialProps: { status: "open" } as Props },
    );
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    rerender({ status: "done" });
    await waitFor(() => expect(apiGet.mock.calls.length).toBe(2));
    expect(apiGet.mock.calls[1][0] as string).toContain("status=done");
  });
});
