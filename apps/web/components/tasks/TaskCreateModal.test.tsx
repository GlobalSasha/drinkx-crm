import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { ...actual.api, post: apiPost },
  };
});

vi.mock("@/lib/hooks/use-leads", () => ({
  useLeads: () => ({ data: { items: [], total: 0 } }),
}));

const { meMock } = vi.hoisted(() => ({ meMock: vi.fn() }));
vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => meMock(),
}));

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({
    data: {
      items: [
        { id: "me-1", email: "head@drinkx.tech", name: "Руководитель", role: "head", last_login_at: null },
        { id: "u2", email: "kirill@drinkx.tech", name: "Кирилл", role: "manager", last_login_at: null },
      ],
      total: 2,
    },
  }),
}));

import { TaskCreateModal } from "./TaskCreateModal";

function renderModal() {
  const qc = new QueryClient();
  const onClose = vi.fn();
  const onCreated = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <TaskCreateModal open onClose={onClose} onCreated={onCreated} />
    </QueryClientProvider>,
  );
  return { onClose, onCreated };
}

describe("TaskCreateModal", () => {
  afterEach(() => {
    apiPost.mockReset();
    meMock.mockReset();
  });

  it("«Поставить» disabled без текста", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    renderModal();
    expect(screen.getByRole("button", { name: "Поставить" })).toBeDisabled();
  });

  it("head — тело содержит выбранный assignee_user_id", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    apiPost.mockResolvedValue({ id: "t1", assignee_user_id: "u2", assignee_name: "Кирилл" });
    renderModal();

    await userEvent.type(screen.getByPlaceholderText("Что нужно сделать"), "Позвонить клиенту");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Исполнитель" }), "u2");
    await userEvent.click(screen.getByRole("button", { name: "Поставить" }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith(
        "/tasks",
        expect.objectContaining({ text: "Позвонить клиенту", assignee_user_id: "u2" }),
      ),
    );
  });

  it("manager — селекта исполнителя нет, assignee_user_id отсутствует в теле", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "manager" } });
    apiPost.mockResolvedValue({ id: "t1", assignee_user_id: "me-1", assignee_name: "Я" });
    renderModal();

    expect(screen.queryByRole("combobox", { name: "Исполнитель" })).not.toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("Что нужно сделать"), "Обновить прайс");
    await userEvent.click(screen.getByRole("button", { name: "Поставить" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    const body = apiPost.mock.calls[0][1] as Record<string, unknown>;
    expect(body).not.toHaveProperty("assignee_user_id");
  });

  it("403 с detail показан, onClose не вызван", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    const { ApiError } = await import("@/lib/api-client");
    apiPost.mockRejectedValue(new ApiError(403, { detail: "Только руководитель может ставить задачи другим" }));
    const { onClose } = renderModal();

    await userEvent.type(screen.getByPlaceholderText("Что нужно сделать"), "Позвонить клиенту");
    await userEvent.click(screen.getByRole("button", { name: "Поставить" }));

    expect(
      await screen.findByText("Только руководитель может ставить задачи другим"),
    ).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
