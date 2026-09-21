/**
 * Постраничная загрузка задач лида (аудит G5, дефект A).
 *
 * Раньше вкладка «Задачи» брала `?type=task&limit=200` у ленты активностей и
 * выбрасывала курсор из ответа. На лиде длиннее двухсот записей открытая
 * задача, заведённая раньше остальных, в интерфейс не попадала: страницы
 * вторая никто не запрашивал.
 *
 * Здесь закреплено то, что должно держаться: первый запрос идёт к
 * `/leads/{id}/tasks`, следующая страница берётся по курсору, строки
 * склеиваются, счётчики описывают всю серверную выборку, а мутация
 * перечитывает все загруженные страницы, а не только первую.
 */
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import type { MyTaskOut, TaskListOut } from "@/lib/types";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: { ...actual.api, get: apiGet, post: apiPost } };
});

import { useLeadTasks, useCompleteLeadTask, LEAD_TASKS_PAGE } from "./use-lead-tasks";

const LEAD = "lead-1";
const CURSOR = "0|2026-01-01T00:00:00+00:00|11111111-1111-1111-1111-111111111111";

function task(id: string, done: boolean): MyTaskOut {
  return {
    id,
    lead_id: LEAD,
    lead_company_name: "Альфа",
    text: `Задача ${id}`,
    task_due_at: null,
    task_done: done,
    task_completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    assignee_user_id: "u1",
    assignee_name: "Кирилл",
    explicit_assignee_user_id: null,
    author_user_id: "u1",
    author_name: "Кирилл",
  };
}

const COUNTS = { total: 251, open: 1, done: 250, overdue: 0 };

/** Открытая задача идёт первой строкой — её сервер ставит впереди. */
const page1: TaskListOut = {
  items: [task("open-1", false), ...Array.from({ length: 49 }, (_, i) => task(`done-${i}`, true))],
  next_cursor: CURSOR,
  counts: COUNTS,
};
const page2: TaskListOut = {
  items: Array.from({ length: 50 }, (_, i) => task(`done-${50 + i}`, true)),
  next_cursor: null,
  counts: COUNTS,
};

function wrapper(qc: QueryClient) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = "TestQueryWrapper";
  return Wrapper;
}

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  apiGet.mockReset().mockImplementation((url: string) =>
    Promise.resolve(url.includes("cursor=") ? page2 : page1),
  );
  apiPost.mockReset().mockResolvedValue({ id: "open-1", lead_id: LEAD });
});

describe("useLeadTasks", () => {
  it("берёт первую страницу у /leads/{id}/tasks и не тянет историю сама", async () => {
    const { result } = renderHook(() => useLeadTasks(LEAD), { wrapper: wrapper(client()) });
    await waitFor(() => expect(result.current.items).toHaveLength(50));

    const urls = apiGet.mock.calls.map(([u]) => u as string);
    expect(urls).toHaveLength(1);
    expect(urls[0]).toBe(`/leads/${LEAD}/tasks?limit=${LEAD_TASKS_PAGE}`);
    // Открытая задача на первой странице — ровно то, чего не было до G5.
    expect(result.current.items[0].id).toBe("open-1");
    expect(result.current.hasNextPage).toBe(true);
  });

  it("счётчики описывают всю выборку, а не загруженную страницу", async () => {
    const { result } = renderHook(() => useLeadTasks(LEAD), { wrapper: wrapper(client()) });
    await waitFor(() => expect(result.current.counts).toBeDefined());
    expect(result.current.items).toHaveLength(50);
    expect(result.current.counts).toEqual(COUNTS);
  });

  it("следующая страница запрашивается по курсору и дописывается к списку", async () => {
    const { result } = renderHook(() => useLeadTasks(LEAD), { wrapper: wrapper(client()) });
    await waitFor(() => expect(result.current.items).toHaveLength(50));

    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.items).toHaveLength(100));

    const second = apiGet.mock.calls[1][0] as string;
    expect(second).toContain(`cursor=${encodeURIComponent(CURSOR)}`);
    expect(result.current.hasNextPage).toBe(false);

    const ids = result.current.items.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("мутация перечитывает все загруженные страницы, а не только первую", async () => {
    const qc = client();
    const w = wrapper(qc);
    const list = renderHook(() => useLeadTasks(LEAD), { wrapper: w });
    await waitFor(() => expect(list.result.current.items).toHaveLength(50));
    await act(async () => {
      await list.result.current.fetchNextPage();
    });
    await waitFor(() => expect(list.result.current.items).toHaveLength(100));

    const before = apiGet.mock.calls.length;
    const complete = renderHook(() => useCompleteLeadTask(LEAD), { wrapper: w });
    await act(async () => {
      await complete.result.current.mutateAsync("open-1");
    });

    // Обе страницы перезапрашиваются: иначе вторая осталась бы с закрытой
    // задачей в прежнем виде до полной перезагрузки экрана.
    await waitFor(() => expect(apiGet.mock.calls.length).toBe(before + 2));
    const refetched = apiGet.mock.calls.slice(before).map(([u]) => u as string);
    expect(refetched.some((u) => !u.includes("cursor="))).toBe(true);
    expect(refetched.some((u) => u.includes("cursor="))).toBe(true);
    expect(list.result.current.items).toHaveLength(100);
  });
});
