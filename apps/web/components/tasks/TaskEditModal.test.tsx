import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

const { apiPatch } = vi.hoisted(() => ({ apiPatch: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { ...actual.api, patch: apiPatch },
  };
});

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

import { TaskEditModal } from "./TaskEditModal";

function renderModal(overrides: Partial<React.ComponentProps<typeof TaskEditModal>> = {}) {
  const qc = new QueryClient();
  const onClose = vi.fn();
  const props: React.ComponentProps<typeof TaskEditModal> = {
    leadId: null,
    taskId: "t1",
    initialTitle: "Старая задача",
    initialDueIso: null,
    onClose,
    ...overrides,
  };
  const result = render(
    <QueryClientProvider client={qc}>
      <TaskEditModal {...props} />
    </QueryClientProvider>,
  );
  return { onClose, unmount: result.unmount };
}

describe("TaskEditModal", () => {
  afterEach(() => {
    apiPatch.mockReset();
    meMock.mockReset();
  });

  it("leadId=null → PATCH /tasks/<id> только с изменёнными полями", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "manager" } });
    apiPatch.mockResolvedValue({ id: "t1", text: "Новая задача" });
    renderModal();

    const input = screen.getByPlaceholderText("Название задачи");
    await userEvent.clear(input);
    await userEvent.type(input, "Новая задача");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(apiPatch).toHaveBeenCalledWith("/tasks/t1", { text: "Новая задача" }),
    );
  });

  it("без изменений — запроса нет и onClose вызван", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "manager" } });
    const { onClose } = renderModal();

    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(apiPatch).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("head видит UserSelect исполнителя, manager — нет", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    const first = renderModal();
    expect(screen.getByRole("combobox", { name: "Исполнитель" })).toBeInTheDocument();
    first.unmount();

    meMock.mockReturnValue({ data: { id: "me-1", role: "manager" } });
    renderModal();
    expect(screen.queryByRole("combobox", { name: "Исполнитель" })).not.toBeInTheDocument();
  });
});
