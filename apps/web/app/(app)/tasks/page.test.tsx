import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const { createTaskMock, meMock, setDoneMock } = vi.hoisted(() => ({
  createTaskMock: vi.fn(),
  meMock: vi.fn(),
  setDoneMock: vi.fn(),
}));

vi.mock("@/lib/hooks/use-tasks", () => ({
  // С G5 хук отдаёт уже склеенные страницы плюс счётчики по всей выборке.
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
  useCreateTask: () => ({ mutateAsync: createTaskMock, isPending: false }),
}));

vi.mock("@/lib/hooks/use-leads", () => ({
  useLeads: () => ({
    data: { items: [], total: 0 },
    isFetching: false,
  }),
}));

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => meMock(),
}));

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({ data: { items: [], total: 0 } }),
}));

import TasksPage from "./page";
import type { MyTaskOut } from "@/lib/types";

const mockTasks = [
  {
    id: "task-1",
    lead_id: "lead-1",
    lead_company_name: "Альфа Ритейл",
    text: "Позвонить закупщику",
    task_due_at: "2026-09-10T09:00:00Z",
    task_done: false,
    task_completed_at: null,
    created_at: "2026-09-09T08:00:00Z",
    assignee_user_id: "me-1",
    assignee_name: "Анна",
    explicit_assignee_user_id: "me-1",
    author_user_id: "head-1",
    author_name: "Руководитель",
  },
  {
    id: "task-2",
    lead_id: null,
    lead_company_name: null,
    text: "Подготовить недельный отчёт",
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-09-09T08:30:00Z",
    assignee_user_id: "me-1",
    assignee_name: "Анна",
    explicit_assignee_user_id: null,
    author_user_id: "me-1",
    author_name: "Анна",
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

describe("TasksPage — доступ к вкладке команды", () => {
  afterEach(() => {
    createTaskMock.mockReset();
    meMock.mockReset();
    setDoneMock.mockReset();
  });

  it("manager видит личные вкладки, но не вкладку и фильтр команды", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "manager" } });
    renderPage();

    expect(screen.getByRole("tab", { name: "Мои" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Поставлено мной" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Команда" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Исполнитель" })).toBeNull();
  });

  it("head видит все три вкладки", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    renderPage();

    expect(screen.getByRole("tab", { name: "Мои" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Поставлено мной" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Команда" })).toBeInTheDocument();
  });

  it("head видит фильтр исполнителя после перехода на вкладку команды", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    renderPage();

    await userEvent.click(screen.getByRole("tab", { name: "Команда" }));

    expect(screen.getByRole("combobox", { name: "Исполнитель" })).toBeInTheDocument();
  });
});
