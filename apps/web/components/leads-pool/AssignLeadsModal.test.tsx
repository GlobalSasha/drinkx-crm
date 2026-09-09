import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const { apiPost, apiGet } = vi.hoisted(() => ({
  apiPost: vi.fn(),
  apiGet: vi.fn(),
}));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { ...actual.api, post: apiPost, get: apiGet },
  };
});

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({
    data: {
      items: [
        { id: "u1", email: "kirill@drinkx.tech", name: "Кирилл", role: "manager", last_login_at: null },
      ],
      total: 1,
    },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => ({ data: { id: "me-1", role: "head" } }),
}));

import { AssignLeadsModal } from "./AssignLeadsModal";

function renderModal(overrides: Partial<React.ComponentProps<typeof AssignLeadsModal>> = {}) {
  const qc = new QueryClient();
  const onClose = vi.fn();
  const onDone = vi.fn();
  const props: React.ComponentProps<typeof AssignLeadsModal> = {
    open: true,
    onClose,
    mode: "selected",
    selectedIds: ["l1", "l2"],
    visibleIds: ["l1", "l2", "l3", "l4"],
    onDone,
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <AssignLeadsModal {...props} />
    </QueryClientProvider>,
  );
  return { onClose, onDone, props };
}

describe("AssignLeadsModal", () => {
  afterEach(() => {
    apiPost.mockReset();
    apiGet.mockReset();
  });

  it("«Выдать» disabled без выбранного менеджера", () => {
    renderModal();
    expect(screen.getByRole("button", { name: "Выдать" })).toBeDisabled();
  });

  it("режим selected шлёт mode:ids, only_pool:true, lead_ids: selectedIds и вызывает onDone", async () => {
    apiPost.mockResolvedValue({ assigned_count: 2, requested: 2, skipped: 0, items: [] });
    const { onDone, onClose } = renderModal({ mode: "selected" });

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Менеджер" }), "u1");
    await userEvent.click(screen.getByRole("button", { name: "Выдать" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/leads/assign", {
      to_user_id: "u1",
      mode: "ids",
      only_pool: true,
      lead_ids: ["l1", "l2"],
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("режим topN с n=2 шлёт первые 2 из visibleIds", async () => {
    apiPost.mockResolvedValue({ assigned_count: 2, requested: 2, skipped: 0, items: [] });
    renderModal({ mode: "topN", visibleIds: ["a", "b", "c", "d"] });

    const nInput = screen.getByLabelText("Сколько выдать");
    await userEvent.clear(nInput);
    await userEvent.type(nInput, "2");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Менеджер" }), "u1");
    await userEvent.click(screen.getByRole("button", { name: "Выдать" }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/leads/assign", {
        to_user_id: "u1",
        mode: "ids",
        only_pool: true,
        lead_ids: ["a", "b"],
      }),
    );
  });

  it("режим topN объясняет невалидное количество", async () => {
    renderModal({ mode: "topN", visibleIds: ["a", "b", "c", "d"] });

    const nInput = screen.getByLabelText("Сколько выдать");
    await userEvent.clear(nInput);
    expect(screen.getByText("Введите число от 1 до 4")).toBeInTheDocument();

    await userEvent.type(nInput, "5");
    expect(screen.getByText("Введите число от 1 до 4")).toBeInTheDocument();

    await userEvent.clear(nInput);
    await userEvent.type(nInput, "2");
    expect(screen.queryByText("Введите число от 1 до 4")).not.toBeInTheDocument();
  });

  it("ошибка API с detail показана и onClose не вызван", async () => {
    const { ApiError } = await import("@/lib/api-client");
    apiPost.mockRejectedValue(new ApiError(400, { detail: "Нет доступных карточек" }));
    const { onClose } = renderModal({ mode: "selected" });

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Менеджер" }), "u1");
    await userEvent.click(screen.getByRole("button", { name: "Выдать" }));

    expect(await screen.findByText("Нет доступных карточек")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
