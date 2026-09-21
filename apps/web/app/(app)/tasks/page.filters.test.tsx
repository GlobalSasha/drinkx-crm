/**
 * TASK-03 (P2-7) — QA дополнение к vitest реализации.
 *
 * Реализация убрала клиентский фильтр «Задач» и передаёт `q`/`due_from`/
 * `due_to` серверу через `useTasks` (queryKey включает фильтры). Хук уже
 * покрыт тестами в lib/hooks/use-tasks-pagination.test.tsx («смена поиска
 * сбрасывает листание», «поиск... уходит в запрос параметрами»). Здесь —
 * то же поведение на уровне самой страницы, с настоящим полем ввода и
 * настоящим debounce (`SEARCH_DEBOUNCE_MS` в page.tsx), которые хук сам по
 * себе не проверяет:
 *
 *   1. Набор текста не шлёт запрос на каждую букву — только один раз, после
 *      паузы (фиксированные таймеры, как в leads-pool/page.server-selection).
 *   2. Смена поиска — новый queryKey, поэтому «Показать ещё» под старым
 *      поиском не подмешивает свою страницу к результату нового.
 *   3. Устаревший ответ (ушёл первым, но пришёл позже второго) не должен
 *      подменить собой то, что показано по актуальному запросу.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MyTaskOut, TaskListOut } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: { ...actual.api, get: apiGet } };
});

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => ({ data: { id: "me-1", role: "manager" }, isLoading: false }),
}));
vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({ data: { items: [], total: 0 } }),
}));

import TasksPage from "./page";

function task(id: string, text: string): MyTaskOut {
  return {
    id,
    lead_id: null,
    lead_company_name: null,
    text,
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-02-01T00:00:00Z",
    assignee_user_id: "me-1",
    assignee_name: "Я",
    explicit_assignee_user_id: "me-1",
    author_user_id: "me-1",
    author_name: "Я",
  };
}

function counts(total: number): TaskListOut["counts"] {
  return { total, open: total, done: 0, overdue: 0 };
}

/** Все запросы списка задач, что реально ушли, в порядке отправки. */
function listCalls(): URL[] {
  return apiGet.mock.calls
    .map(([u]) => u as string)
    .filter((u) => u.startsWith("/tasks"))
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
      <TasksPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useRealTimers();
  apiGet.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Задачи — поиск и срок отбираются на сервере (TASK-03)", () => {
  it("набор текста не шлёт запрос на каждую букву — один раз, после паузы", async () => {
    apiGet.mockImplementation((url: string) =>
      Promise.resolve({
        items: [task("t1", "Первая задача")],
        next_cursor: null,
        counts: counts(1),
      } satisfies TaskListOut),
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(0));
    const before = listCalls().length;

    await user.type(
      screen.getByPlaceholderText(/Поиск по клиенту или задаче/),
      "Уникальный",
    );
    // Пока идёт набор (меньше паузы 300мс между символами), новых запросов
    // быть не должно — иначе 10 букв дали бы 10 запросов.
    expect(listCalls().length).toBe(before);

    vi.advanceTimersByTime(400);
    await waitFor(() => expect(lastList().searchParams.get("q")).toBe("Уникальный"));
    // Один запрос на весь набранный текст, а не по одному на символ.
    expect(listCalls().length).toBe(before + 1);
  });

  it("смена поиска сбрасывает листание: старая страница не подмешивается к новому фильтру", async () => {
    apiGet.mockImplementation((url: string) => {
      const q = new URL(url, "http://test").searchParams.get("q");
      const hasCursor = new URL(url, "http://test").searchParams.has("cursor");
      if (q === "альфа" && !hasCursor) {
        return Promise.resolve({
          items: [task("a1", "Альфа один")],
          next_cursor: "CURSOR-ALPHA",
          counts: counts(2),
        } satisfies TaskListOut);
      }
      if (q === "альфа" && hasCursor) {
        return Promise.resolve({
          items: [task("a2", "Альфа два")],
          next_cursor: null,
          counts: counts(2),
        } satisfies TaskListOut);
      }
      if (q === "бета") {
        return Promise.resolve({
          items: [task("b1", "Бета один")],
          next_cursor: null,
          counts: counts(1),
        } satisfies TaskListOut);
      }
      return Promise.resolve({ items: [], next_cursor: null, counts: counts(0) } satisfies TaskListOut);
    });

    renderPage();
    const input = screen.getByPlaceholderText(/Поиск по клиенту или задаче/);
    await userEvent.type(input, "альфа");
    await waitFor(() => expect(screen.getByText("Альфа один")).toBeInTheDocument());

    // Дотягиваем вторую страницу под «альфа».
    await userEvent.click(await screen.findByRole("button", { name: "Показать ещё" }));
    await waitFor(() => expect(screen.getByText("Альфа два")).toBeInTheDocument());

    // Меняем поиск — обе строки «альфа» должны исчезнуть, без курсора.
    await userEvent.clear(input);
    await userEvent.type(input, "бета");
    await waitFor(() => expect(screen.getByText("Бета один")).toBeInTheDocument());

    expect(screen.queryByText("Альфа один")).not.toBeInTheDocument();
    expect(screen.queryByText("Альфа два")).not.toBeInTheDocument();
    expect(lastList().searchParams.has("cursor")).toBe(false);
  });

  it("устаревший ответ, пришедший позже, не подменяет актуальный результат", async () => {
    let resolveStale: (v: TaskListOut) => void = () => {};
    const stale = new Promise<TaskListOut>((resolve) => {
      resolveStale = resolve;
    });

    apiGet.mockImplementation((url: string) => {
      const q = new URL(url, "http://test").searchParams.get("q");
      if (q === "первый") return stale; // намеренно зависает
      if (q === "второй") {
        return Promise.resolve({
          items: [task("v2", "Второй результат")],
          next_cursor: null,
          counts: counts(1),
        } satisfies TaskListOut);
      }
      return Promise.resolve({ items: [], next_cursor: null, counts: counts(0) } satisfies TaskListOut);
    });

    renderPage();
    const input = screen.getByPlaceholderText(/Поиск по клиенту или задаче/);

    // Первый поиск уходит и «зависает» (ответ ещё не пришёл).
    await userEvent.type(input, "первый");
    await waitFor(() => expect(listCalls().some((u) => u.searchParams.get("q") === "первый")).toBe(true));

    // Меняем запрос до того, как первый ответил — это уже другой queryKey.
    await userEvent.clear(input);
    await userEvent.type(input, "второй");
    await waitFor(() => expect(screen.getByText("Второй результат")).toBeInTheDocument());

    // Первый («устаревший») ответ приходит с опозданием — он не должен
    // затереть уже показанный результат второго запроса.
    resolveStale({
      items: [task("v1", "Первый результат (устарел)")],
      next_cursor: null,
      counts: counts(1),
    });
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByText("Второй результат")).toBeInTheDocument();
    expect(screen.queryByText("Первый результат (устарел)")).not.toBeInTheDocument();
  });
});
