/**
 * A failed task action has to be visible, and must not eat the input (G3).
 *
 * Delegation used to close its selector on the same tick as `mutate`, so a
 * refusal left no selector, no chosen value and no message — the row simply
 * looked unchanged. Creating and completing failed just as quietly.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiGet, apiPost, apiPatch, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { ...actual.api, get: apiGet, post: apiPost, patch: apiPatch, delete: apiDelete },
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
      ],
      total: 2,
    },
  }),
}));

import { ApiError } from "@/lib/api-client";
import { TasksTab } from "./TasksTab";

const LEAD = "lead-1";
// С G5 вкладка читает GET /leads/{id}/tasks — форма строки MyTaskOut, ответ
// со счётчиками и курсором.
const TASK = {
  id: "act-1",
  lead_id: LEAD,
  lead_company_name: "Альфа",
  text: "Позвонить клиенту",
  task_due_at: null,
  task_done: false,
  task_completed_at: null,
  created_at: "2026-09-20T10:00:00Z",
  assignee_user_id: "head-1",
  assignee_name: "Руководитель",
  explicit_assignee_user_id: null,
  author_user_id: "head-1",
  author_name: "Руководитель",
};
const TASK_PAGE = {
  items: [TASK],
  next_cursor: null,
  counts: { total: 1, open: 1, done: 0, overdue: 0 },
};

function renderTab() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <TasksTab leadId={LEAD} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiGet.mockReset().mockResolvedValue(TASK_PAGE);
  apiPost.mockReset();
  apiPatch.mockReset();
  apiDelete.mockReset();
});

describe("TasksTab — a refused action", () => {
  it("keeps the delegate selector open and says why", async () => {
    apiPatch.mockRejectedValue(
      new ApiError(403, { detail: "Ставить задачи другим может только руководитель или админ" }),
    );
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("Позвонить клиенту");

    await user.click(screen.getByRole("button", { name: /поручить/i }));
    const select = await screen.findByLabelText("Кому поручить задачу");
    await user.selectOptions(select, "mgr-1");

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Ставить задачи другим может только руководитель или админ",
      ),
    );
    // The selector is still there, still holding what was chosen.
    expect(screen.getByLabelText("Кому поручить задачу")).toHaveValue("mgr-1");
  });

  it("closes the delegate selector only once the server agrees", async () => {
    apiPatch.mockResolvedValue({ id: "act-1", lead_id: LEAD });
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("Позвонить клиенту");

    await user.click(screen.getByRole("button", { name: /поручить/i }));
    await user.selectOptions(await screen.findByLabelText("Кому поручить задачу"), "mgr-1");

    await waitFor(() =>
      expect(screen.queryByLabelText("Кому поручить задачу")).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the typed text when creating fails", async () => {
    apiPost.mockRejectedValue(new ApiError(400, { detail: "текст задачи не может быть пустым" }));
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("Позвонить клиенту");

    await user.click(screen.getByRole("button", { name: /добавить задачу/i }));
    const input = await screen.findByPlaceholderText(/название задачи/i);
    await user.type(input, "Новая задача");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByPlaceholderText(/название задачи/i)).toHaveValue("Новая задача");
  });

  it("reports a failed completion instead of doing nothing", async () => {
    apiPost.mockRejectedValue(new ApiError(500, { detail: "Внутренняя ошибка" }));
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("Позвонить клиенту");

    await user.click(screen.getByRole("button", { name: /отметить выполненной|выполнено/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Внутренняя ошибка"),
    );
  });
});
