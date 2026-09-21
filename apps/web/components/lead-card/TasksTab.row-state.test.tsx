/**
 * TASK-01 (P2-2) — oracle-тесты по фиксированному контракту, написаны ДО
 * починки. Контракт: apps/web/components/lead-card/TasksTab.tsx:74 держит
 * ОДИН на весь список `useState(pendingAssignee)` и один `useUpdateTask()`
 * (`update.isError` / `update.isPending` общие на все строки), поэтому
 * ошибка или pending одной задачи протекает в селектор другой.
 *
 * TASK-ROW-01 на текущем коде (6e774c2) ожидаемо падает — это контрпример,
 * не баг теста. Не подгонять под PASS без починки компонента.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { MyTaskOut } from "@/lib/types";

const { apiPatch } = vi.hoisted(() => ({
  apiPatch: vi.fn(),
}));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { ...actual.api, patch: apiPatch },
  };
});

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => ({ data: { id: "head-1", role: "head", name: "Руководитель" } }),
}));

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({
    data: {
      items: [
        { id: "head-1", email: "head@drinkx.tech", name: "Руководитель", role: "head", last_login_at: null },
        { id: "mgr-1", email: "kirill@drinkx.tech", name: "Кирилл", role: "manager", last_login_at: null },
        { id: "mgr-2", email: "petr@drinkx.tech", name: "Пётр", role: "manager", last_login_at: null },
      ],
      total: 3,
    },
  }),
}));

const leadTasksState = vi.hoisted(() => ({
  items: [] as MyTaskOut[],
}));

vi.mock("@/lib/hooks/use-lead-tasks", () => ({
  useLeadTasks: () => ({
    items: leadTasksState.items,
    counts: {
      total: leadTasksState.items.length,
      open: leadTasksState.items.length,
      done: 0,
      overdue: 0,
    },
    isLoading: false,
    isError: false,
    hasNextPage: false,
    fetchNextPage: vi.fn(),
    isFetchingNextPage: false,
  }),
  useCreateLeadTask: () => ({ mutate: vi.fn(), isPending: false }),
  useCompleteLeadTask: () => ({ mutate: vi.fn(), isPending: false }),
  useReopenLeadTask: () => ({ mutate: vi.fn(), isPending: false }),
  useArchiveLeadTask: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { ApiError } from "@/lib/api-client";
import { TasksTab } from "./TasksTab";

const LEAD = "lead-1";

function task(id: string, text: string, explicitAssignee: string | null = null): MyTaskOut {
  return {
    id,
    lead_id: LEAD,
    lead_company_name: "Альфа",
    text,
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-09-20T10:00:00Z",
    assignee_user_id: "head-1",
    assignee_name: "Руководитель",
    explicit_assignee_user_id: explicitAssignee,
    author_user_id: "head-1",
    author_name: "Руководитель",
  };
}

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderTab(qc: QueryClient = makeQueryClient()) {
  return render(
    <QueryClientProvider client={qc}>
      <TasksTab leadId={LEAD} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiPatch.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("TASK-ROW-01 — ошибка делегирования одной строки не должна протекать в другую", () => {
  it("после ошибки у задачи 1 селектор задачи 2 показывает своего исполнителя, без чужой ошибки", async () => {
    leadTasksState.items = [
      task("t1", "Позвонить клиенту"),
      task("t2", "Отправить КП"),
    ];
    apiPatch.mockRejectedValue(
      new ApiError(403, { detail: "Ставить задачи другим может только руководитель или админ" }),
    );

    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[0]);
    const select1 = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select1, "mgr-1");

    // Дожидаемся, что ошибка действительно отразилась в UI задачи 1.
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    // Открываем делегирование у задачи 2 — селектор задачи 1 закрывается.
    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[1]);
    const select2 = await screen.findByLabelText("Кому поручить задачу");

    // Контрпример: у задачи 2 нет explicit_assignee_user_id — селектор
    // должен быть пуст, а не показывать "mgr-1", выбранный в задаче 1.
    // На текущем коде (общий pendingAssignee + общий update.isError)
    // здесь ожидаемо падение.
    expect(select2).toHaveValue("");

    // Чужая ошибка тоже не должна отображаться под задачей 2.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("TASK-ROW-02 — pending одной строки не должен задевать другую", () => {
  it("pending задачи 1 не дизейблит и не подставляет значение в селектор задачи 2", async () => {
    leadTasksState.items = [
      task("t1", "Позвонить клиенту"),
      task("t2", "Отправить КП"),
    ];
    let resolvePatch: (v: MyTaskOut) => void = () => {};
    apiPatch.mockImplementation(
      () =>
        new Promise<MyTaskOut>((resolve) => {
          resolvePatch = resolve;
        }),
    );

    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[0]);
    const select1 = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select1, "mgr-1"); // запрос зависает в pending

    // Открываем задачу 2, пока задача 1 всё ещё pending.
    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[1]);
    const select2 = await screen.findByLabelText("Кому поручить задачу");

    expect(select2).not.toBeDisabled();
    expect(select2).toHaveValue("");

    resolvePatch(task("t1", "Позвонить клиенту", "mgr-1"));
  });

  it("состояние делегирования остаётся привязано к id задачи при смене порядка списка", async () => {
    leadTasksState.items = [
      task("t1", "Позвонить клиенту"),
      task("t2", "Отправить КП", "mgr-2"),
    ];

    const user = userEvent.setup();
    const qc = makeQueryClient();
    const { rerender } = renderTab(qc);

    // Открываем делегирование у задачи 1 (первая в списке, без своего исполнителя).
    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[0]);
    expect(await screen.findByLabelText("Кому поручить задачу")).toHaveValue("");

    // Переставляем порядок массива: задача 2 теперь первая.
    leadTasksState.items = [leadTasksState.items[1], leadTasksState.items[0]];
    rerender(
      <QueryClientProvider client={qc}>
        <TasksTab leadId={LEAD} />
      </QueryClientProvider>,
    );

    // Делегирование должно остаться на задаче 1 (по id), а не "прилипнуть"
    // к позиции 0, где теперь задача 2 со своим mgr-2.
    const select = screen.getByLabelText("Кому поручить задачу");
    expect(select).toHaveValue("");
  });
});

describe("TASK-ROW-03 — успешная делегация и блокировка double submit", () => {
  it("успех обновляет кэш задач лида и закрывает селектор", async () => {
    leadTasksState.items = [task("t1", "Позвонить клиенту")];
    apiPatch.mockResolvedValue(task("t1", "Позвонить клиенту", "mgr-1"));

    const user = userEvent.setup();
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    renderTab(qc);

    await user.click(screen.getByTitle("Поручить задачу сотруднику"));
    await user.selectOptions(await screen.findByLabelText("Кому поручить задачу"), "mgr-1");

    await waitFor(() =>
      expect(screen.queryByLabelText("Кому поручить задачу")).not.toBeInTheDocument(),
    );

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["activities", LEAD, "task"] }),
    );
    expect(apiPatch).toHaveBeenCalledTimes(1);
  });

  it("повторный выбор во время pending не вызывает mutate второй раз", async () => {
    leadTasksState.items = [task("t1", "Позвонить клиенту")];
    let resolvePatch: (v: MyTaskOut) => void = () => {};
    apiPatch.mockImplementation(
      () =>
        new Promise<MyTaskOut>((resolve) => {
          resolvePatch = resolve;
        }),
    );

    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByTitle("Поручить задачу сотруднику"));
    const select = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select, "mgr-1");

    expect(apiPatch).toHaveBeenCalledTimes(1);
    expect(select).toBeDisabled();

    // Пока запрос висит, попытка снова изменить значение не должна дойти
    // до второго mutate (UI держит select задизейбленным).
    fireEvent.change(select, { target: { value: "mgr-2" } });
    expect(apiPatch).toHaveBeenCalledTimes(1);

    resolvePatch(task("t1", "Позвонить клиенту", "mgr-1"));
  });
});

describe("TASK-ROW-02b — общий mutation-объект: race между двумя строками", () => {
  it("успех задачи 1, пришедший после того как открыта и выбрана задача 2, не должен закрывать/сбрасывать ещё not-resolved состояние задачи 2", async () => {
    leadTasksState.items = [
      task("t1", "Позвонить клиенту"),
      task("t2", "Отправить КП"),
    ];
    const resolvers: Array<(v: MyTaskOut) => void> = [];
    apiPatch.mockImplementation(
      () =>
        new Promise<MyTaskOut>((resolve) => {
          resolvers.push(resolve);
        }),
    );

    const user = userEvent.setup();
    renderTab();

    // Задача 1: открыть и выбрать — запрос 1 висит.
    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[0]);
    const select1 = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select1, "mgr-1");
    expect(apiPatch).toHaveBeenCalledTimes(1);

    // Задача 2: открыть (закрывает UI задачи 1, т.к. delegatingId один) и
    // выбрать — запрос 2 висит одновременно с запросом 1, на одном and
    // том же useMutation()-объекте.
    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[1]);
    const select2 = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select2, "mgr-2");
    expect(apiPatch).toHaveBeenCalledTimes(2);
    expect(select2).toBeDisabled();

    // Запрос 1 (задача 1) резолвится ПОСЛЕ того, как выбор сделан по
    // задаче 2, и её запрос ещё не завершился.
    resolvers[0](task("t1", "Позвонить клиенту", "mgr-1"));

    await waitFor(() => {
      // Ожидаемый контракт (TASK-ROW-02): успех задачи 1 не должен
      // трогать состояние задачи 2, чей запрос ещё висит — селектор
      // задачи 2 должен остаться открытым и задизейбленным.
      const stillOpen = screen.queryByLabelText("Кому поручить задачу");
      expect(stillOpen).not.toBeNull();
    });

    resolvers[1](task("t2", "Отправить КП", "mgr-2"));
  });
});

describe("TASK-ROW-02c — общий mutation-объект: ошибка задачи 1 теряется, если задачу 2 успели тронуть раньше", () => {
  it("отказ по задаче 1, пришедший после того как выбор сделан по задаче 2, нигде не показывается", async () => {
    leadTasksState.items = [
      task("t1", "Позвонить клиенту"),
      task("t2", "Отправить КП"),
    ];
    const handlers: Array<{
      resolve: (v: MyTaskOut) => void;
      reject: (e: unknown) => void;
    }> = [];
    apiPatch.mockImplementation(
      () =>
        new Promise<MyTaskOut>((resolve, reject) => {
          handlers.push({ resolve, reject });
        }),
    );

    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[0]);
    const select1 = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select1, "mgr-1"); // запрос 1 в пути

    await user.click(screen.getAllByTitle("Поручить задачу сотруднику")[1]);
    const select2 = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select2, "mgr-2"); // запрос 2 в пути, владение перешло к задаче 2

    // Запрос 1 отказывает уже после того, как активной стала задача 2.
    handlers[0].reject(
      new ApiError(403, { detail: "Ставить задачи другим может только руководитель или админ" }),
    );

    // Общий update.isError отслеживает только ПОСЛЕДНИЙ вызванный mutate
    // (задачу 2), поэтому отказ задачи 1 нигде не появляется — ни как
    // чужая ошибка у задачи 2 (это и есть цель контракта), ни как
    // собственная ошибка у задачи 1 (это остаточный риск: обратная связь
    // по первой задаче молча теряется).
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("alert")).toBeNull();

    handlers[1].resolve(task("t2", "Отправить КП", "mgr-2"));
  });
});
