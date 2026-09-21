// TASK-02 (P2-6): модалка /tasks закрепляет вычисленного исполнителя.
//
// MyTaskOut различает `assignee_user_id` (уже разрешённый — явный, иначе
// владелец лида, иначе автор) и `explicit_assignee_user_id` (что реально
// записано в задаче; null = «делает владелец лида/автор»). TaskRow
// (apps/web/lib/tasks.ts) хранит только `assigneeId = t.assignee_user_id`
// — то есть УЖЕ РАЗРЕШЁННОЕ значение, explicit нигде не долетает до
// TaskEditModal. Модалка получает его как `initialAssigneeId` и сравнивает
// с ним же после правки (apps/web/components/tasks/TaskEditModal.tsx):
// `if (canReassign && assigneeId !== initialAssigneeId) body.assignee_user_id
// = assigneeId`. Раз оба конца сравнения — один и тот же эффективный id,
// PATCH без прикосновения к селектору ключ не пришлёт (см. TASK-EXPLICIT-01
// ниже — это НЕ ломается). Но ровно по той же причине у головы/админа НЕТ
// способа увидеть «это неявно» и НЕТ способа снять явное назначение назад
// к «по лиду/по автору» — у UserSelect в TaskEditModal не передан
// `allowEmpty`, пункта «— не выбран —» в разметке нет (TASK-EXPLICIT-03).
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const { apiPatch } = vi.hoisted(() => ({ apiPatch: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { ...actual.api, patch: apiPatch },
  };
});

const { meMock, setDoneMock } = vi.hoisted(() => ({
  meMock: vi.fn(),
  setDoneMock: vi.fn(),
}));

vi.mock("@/lib/hooks/use-tasks", async () => {
  const actual = await vi.importActual<typeof import("@/lib/hooks/use-tasks")>(
    "@/lib/hooks/use-tasks",
  );
  return {
    ...actual,
    // useUpdateTask / useCreateTask остаются настоящими — они дойдут до
    // замоканного api.patch/api.post и мы увидим реальный payload.
    useTasks: () => ({
      items: mockTasks,
      counts: { total: mockTasks.length, open: mockTasks.length, done: 0, overdue: 0 },
      isPending: false,
      isError: false,
      hasNextPage: false,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    }),
    useSetTaskDone: () => ({ mutate: setDoneMock, isPending: false }),
  };
});

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => meMock(),
}));

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({
    data: {
      items: [
        { id: "head-1", email: "head@drinkx.tech", name: "Руководитель", role: "head", last_login_at: null },
        { id: "owner-1", email: "owner@drinkx.tech", name: "Владелец", role: "manager", last_login_at: null },
        { id: "helper-1", email: "helper@drinkx.tech", name: "Помощник", role: "manager", last_login_at: null },
      ],
      total: 3,
    },
  }),
}));

import TasksPage from "./page";
import type { MyTaskOut } from "@/lib/types";

// task-implicit: лидовая задача, явного исполнителя нет — «эффективный»
// (assignee_user_id) — владелец лида ("owner-1"). Это ровно случай, который
// TaskRow/TaskEditModal видят как единственное значение.
//
// ПОСЛЕ ПРАВКИ TASK-02: `TaskRow.explicitAssigneeId` несёт explicit, модалка
// получает его как `initialAssigneeId`, а вычисленного человека показывает
// подписью пустого пункта («По умолчанию: <имя>»). Ожидания ниже помечены
// «было/стало».
// task-standalone: задача без лида (lead_id=null), явного исполнителя нет —
// эффективный резолвится в автора ("head-1" сам себе поставил).
const mockTasks = [
  {
    id: "task-implicit",
    lead_id: "lead-1",
    lead_company_name: "Альфа Ритейл",
    text: "Позвонить закупщику",
    task_due_at: "2026-09-10T09:00:00Z",
    task_done: false,
    task_completed_at: null,
    created_at: "2026-09-09T08:00:00Z",
    assignee_user_id: "owner-1",
    assignee_name: "Владелец",
    explicit_assignee_user_id: null,
    author_user_id: "head-1",
    author_name: "Руководитель",
  },
  {
    id: "task-standalone",
    lead_id: null,
    lead_company_name: null,
    text: "Сдать недельный отчёт",
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-09-09T08:30:00Z",
    assignee_user_id: "head-1",
    assignee_name: "Руководитель",
    explicit_assignee_user_id: null,
    author_user_id: "head-1",
    author_name: "Руководитель",
  },
  {
    id: "task-explicit",
    lead_id: "lead-2",
    lead_company_name: "Бета Опт",
    text: "Согласовать отсрочку",
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-09-09T09:00:00Z",
    // Явно поручено помощнику: эффективный и явный совпадают, но это
    // именно явное назначение — его и должно быть видно в селекторе.
    assignee_user_id: "helper-1",
    assignee_name: "Помощник",
    explicit_assignee_user_id: "helper-1",
    author_user_id: "head-1",
    author_name: "Руководитель",
  },
] satisfies MyTaskOut[];

function renderPage() {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <TasksPage />
    </QueryClientProvider>,
  );
}

async function openEditModalFor(taskText: string) {
  const row = screen.getByText(taskText).closest("tr");
  if (!row) throw new Error(`row not found for "${taskText}"`);
  const editBtn = within(row).getByTitle("Редактировать задачу");
  await userEvent.click(editBtn);
}

describe("TASK-EXPLICIT-01 — правка текста без прикосновения к исполнителю", () => {
  afterEach(() => {
    apiPatch.mockReset();
    meMock.mockReset();
  });

  it("PATCH не должен закреплять вычисленного (эффективного) исполнителя как явного", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    apiPatch.mockResolvedValue({ ...mockTasks[0], text: "Позвонить закупщику ещё раз" });
    renderPage();

    await openEditModalFor("Позвонить закупщику");

    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    // БЫЛО: селектор показывал "owner-1" (вычисленного владельца лида) —
    // визуально неотличимо от явного назначения. СТАЛО: пустое значение,
    // то есть «по умолчанию», а имя вычисленного человека — в подписи
    // пустого пункта (см. TASK-EXPLICIT-04 ниже).
    expect((selector as HTMLSelectElement).value).toBe("");

    const titleInput = screen.getByPlaceholderText("Название задачи");
    await userEvent.type(titleInput, " ещё раз");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
    const [, body] = apiPatch.mock.calls[0];
    // Ключа нет — и теперь по правильной причине: сравнение идёт
    // explicit-с-explicit (null против null). Верни маппинг
    // effective→value формы — и здесь снова появится assignee_user_id.
    expect(body).not.toHaveProperty("assignee_user_id");
    expect(body).toEqual({ text: "Позвонить закупщику ещё раз" });
  });
});

describe("TASK-EXPLICIT-02 — явный выбор исполнителя", () => {
  afterEach(() => {
    apiPatch.mockReset();
    meMock.mockReset();
  });

  it("выбор нового исполнителя уходит как UUID", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    apiPatch.mockResolvedValue({ ...mockTasks[0], assignee_user_id: "helper-1" });
    renderPage();

    await openEditModalFor("Позвонить закупщику");
    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    await userEvent.selectOptions(selector, "helper-1");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
    const [, body] = apiPatch.mock.calls[0];
    expect(body).toEqual({ assignee_user_id: "helper-1" });
  });

  it("manager не видит селектор исполнителя вовсе (сервер вернёт 403, если обойти UI)", async () => {
    meMock.mockReturnValue({ data: { id: "owner-1", role: "manager" } });
    renderPage();

    await openEditModalFor("Позвонить закупщику");
    expect(screen.queryByRole("combobox", { name: "Исполнитель" })).not.toBeInTheDocument();
    // Серверный 403 для manager, пытающегося переназначить чужую задачу —
    // apps/api/tests/test_task_contract.py::test_a_manager_cannot_assign_a_colleague
    // и ::test_a_manager_cannot_use_null_to_push_work_onto_the_lead_owner.
  });
});

describe("TASK-EXPLICIT-03 — «снять» явного исполнителя через модалку", () => {
  afterEach(() => {
    apiPatch.mockReset();
    meMock.mockReset();
  });

  it("у UserSelect есть пустой пункт — allowEmpty передан", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    renderPage();

    await openEditModalFor("Сдать недельный отчёт");
    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    const optionValues = Array.from(selector.querySelectorAll("option")).map(
      (o) => (o as HTMLOptionElement).value,
    );
    // было: пункта "" не было вовсе, снять явное назначение было нечем.
    expect(optionValues).toContain("");
  });

  it("clear через модалку уходит как assignee_user_id: null", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    apiPatch.mockResolvedValue({ ...mockTasks[2], explicit_assignee_user_id: null });
    renderPage();

    // Задача с ЯВНЫМ исполнителем ("helper-1"): голова снимает его и
    // возвращает задачу к «по умолчанию». По контракту backend это null,
    // а не omitted и не чужой UUID
    // (apps/api/tests/test_task_contract.py::
    //  test_null_clears_the_explicit_assignee_back_to_the_lead_owner).
    await openEditModalFor("Согласовать отсрочку");
    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    expect((selector as HTMLSelectElement).value).toBe("helper-1");

    await userEvent.selectOptions(selector, "");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
    const [, body] = apiPatch.mock.calls[0];
    expect(body).toEqual({ assignee_user_id: null });
  });
});

describe("TASK-EXPLICIT-04 — «по умолчанию» видно, а не угадывается", () => {
  afterEach(() => {
    apiPatch.mockReset();
    meMock.mockReset();
  });

  it("пустой пункт подписан именем вычисленного исполнителя", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    renderPage();

    await openEditModalFor("Позвонить закупщику");
    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    const empty = Array.from(selector.querySelectorAll("option")).find(
      (o) => (o as HTMLOptionElement).value === "",
    );
    // Задача лидовая, explicit пуст, вычисленный — владелец лида «Владелец».
    expect(empty?.textContent).toBe("По умолчанию: Владелец");
    expect((selector as HTMLSelectElement).value).toBe("");
  });

  it("у задачи с явным исполнителем выбран он сам, а не вычисленный", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    renderPage();

    await openEditModalFor("Согласовать отсрочку");
    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    expect((selector as HTMLSelectElement).value).toBe("helper-1");
  });

  it("у задачи с явным исполнителем пустой пункт не подписан его же именем", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    renderPage();

    // UX-DELTA-002. «Согласовать отсрочку» явно поручена Помощнику, и
    // вычисленный исполнитель равен явному. Подпись «По умолчанию:
    // Помощник» читалась бы как «снимешь выбор — останется тот же
    // человек», хотя по умолчанию задача уйдёт владельцу лида.
    await openEditModalFor("Согласовать отсрочку");
    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    const empty = Array.from(selector.querySelectorAll("option")).find(
      (o) => (o as HTMLOptionElement).value === "",
    );
    expect(empty?.textContent).not.toContain("Помощник");
    // Задача лидовая — кто именно владелец, строка списка не знает.
    expect(empty?.textContent).toBe("По умолчанию: владелец лида");
  });
});
