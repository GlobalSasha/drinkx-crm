/**
 * Проверка прав на делегирование задач живёт только во фронтенде, на уровне разметки:
 * менеджер не должен видеть выбор исполнителя и кнопку «Поручить», а руководитель — должен.
 * Эти проверки легко потерять при правке компонента, поэтому они закреплены тестами.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { MyTaskOut } from "@/lib/types";

import { TasksTab } from "./TasksTab";

const state = vi.hoisted(() => ({ role: "manager" as string }));

vi.mock("@/lib/hooks/use-lead-tasks", () => {
  const task = {
    id: "t1",
    lead_id: "lead-1",
    lead_company_name: "Альфа",
    text: "Позвонить клиенту",
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    assignee_user_id: "me",
    assignee_name: "Кирилл",
    explicit_assignee_user_id: null,
    author_user_id: "me",
    author_name: "Кирилл",
  } satisfies MyTaskOut;

  return {
    useLeadTasks: () => ({
      items: [task],
      counts: { total: 1, open: 1, done: 0, overdue: 0 },
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
  };
});

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => ({ data: { id: "me", role: state.role } }),
}));

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({
    data: {
      items: [
        { id: "me", email: "boss@x.ru", name: "Кирилл", role: "head", last_login_at: null },
        { id: "u2", email: "mgr@x.ru", name: "Пётр", role: "manager", last_login_at: null },
      ],
    },
  }),
}));

vi.mock("@/lib/hooks/use-tasks", () => ({
  useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
}));

afterEach(() => {
  cleanup();
});

describe("TasksTab — права на делегирование", () => {
  it("менеджер не видит выбор исполнителя в форме", async () => {
    state.role = "manager";
    const user = userEvent.setup();
    render(<TasksTab leadId="lead-1" />);

    await user.click(screen.getByRole("button", { name: "Добавить задачу" }));

    expect(screen.queryByLabelText("Исполнитель задачи")).toBeNull();
  });

  it("менеджер не видит кнопку «Поручить»", () => {
    state.role = "manager";
    render(<TasksTab leadId="lead-1" />);

    expect(screen.queryByTitle("Поручить задачу сотруднику")).toBeNull();
  });

  it("руководитель видит выбор исполнителя в форме", async () => {
    state.role = "head";
    const user = userEvent.setup();
    render(<TasksTab leadId="lead-1" />);

    await user.click(screen.getByRole("button", { name: "Добавить задачу" }));

    expect(screen.getByLabelText("Исполнитель задачи")).toBeInTheDocument();
  });

  it("руководитель видит кнопку «Поручить» и раскрывает выбор", async () => {
    state.role = "head";
    const user = userEvent.setup();
    render(<TasksTab leadId="lead-1" />);

    await user.click(screen.getByTitle("Поручить задачу сотруднику"));

    expect(screen.getByLabelText("Кому поручить задачу")).toBeInTheDocument();
  });
});
