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
    // Контрпример: селектор уже показывает "owner-1" (эффективного
    // владельца лида) как выбранное значение — хотя в задаче явного
    // исполнителя нет (explicit_assignee_user_id === null). У головы нет
    // возможности увидеть, что это не явное назначение.
    expect((selector as HTMLSelectElement).value).toBe("owner-1");

    const titleInput = screen.getByPlaceholderText("Название задачи");
    await userEvent.type(titleInput, " ещё раз");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
    const [, body] = apiPatch.mock.calls[0];
    // Фактическое поведение сегодняшнего кода: сравнение assigneeId с тем
    // же initialAssigneeId (оба — эффективный "owner-1") не даёт разницы,
    // поэтому assignee_user_id в PATCH отсутствует. Явный исполнитель
    // ПОКА не проставляется случайно этим конкретным путём — записываем
    // это как факт, а не как гарантию: initialAssigneeId в принципе не тот
    // источник (эффективный, а не explicit_assignee_user_id), и любая
    // логика, которая станет сравнивать иначе, тихо сломает этот инвариант.
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

describe("TASK-EXPLICIT-03 — «снять» явного исполнителя невозможно через эту модалку", () => {
  afterEach(() => {
    apiPatch.mockReset();
    meMock.mockReset();
  });

  it("UserSelect в TaskEditModal не предлагает пустой пункт — allowEmpty не передан", async () => {
    meMock.mockReturnValue({ data: { id: "head-1", role: "head" } });
    renderPage();

    await openEditModalFor("Сдать недельный отчёт");
    const selector = await screen.findByRole("combobox", { name: "Исполнитель" });
    const optionValues = Array.from(selector.querySelectorAll("option")).map(
      (o) => (o as HTMLOptionElement).value,
    );
    // Контрпример: нет пункта со значением "" ("— не выбран —" / «по
    // умолчанию»), поэтому явное присвоение нельзя вернуть к null через
    // эту форму — только выбрать другого конкретного человека, что снова
    // не совпадает с "снять" (по контракту backend — вернуть к автору,
    // см. apps/api/tests/test_task_contract.py::test_clearing_a_standalone_task_returns_it_to_its_author).
    expect(optionValues).not.toContain("");
  });
});
