import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

// Кто приглашает: админ и руководитель — да, менеджер — нет.
// Роль «Админ» в списке видит только админ (сервер откажет в любом случае,
// селект просто не предлагает заведомо мёртвый вариант).

const { meMock } = vi.hoisted(() => ({ meMock: vi.fn() }));
vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => meMock(),
}));

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({
    data: {
      items: [
        {
          id: "me-1",
          email: "boss@drinkx.tech",
          name: "Руководитель",
          role: "head",
          last_login_at: null,
        },
      ],
      total: 1,
    },
  }),
  useUserInvites: () => ({ data: [] }),
  useInviteUser: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteUser: () => ({ mutate: vi.fn(), isPending: false }),
  useChangeUserRole: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { TeamSection } from "./TeamSection";

function renderSection() {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <TeamSection />
    </QueryClientProvider>,
  );
}

const inviteButton = () => screen.queryByRole("button", { name: /Пригласить/ });

describe("TeamSection — кто может приглашать", () => {
  afterEach(() => {
    meMock.mockReset();
  });

  it("руководитель видит кнопку «Пригласить»", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    renderSection();
    expect(inviteButton()).toBeInTheDocument();
  });

  it("админ видит кнопку «Пригласить»", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "admin" } });
    renderSection();
    expect(inviteButton()).toBeInTheDocument();
  });

  it("менеджер кнопку не видит", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "manager" } });
    renderSection();
    expect(inviteButton()).not.toBeInTheDocument();
  });

  it("руководителю не предлагают роль «Админ»", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    renderSection();
    await userEvent.click(inviteButton()!);

    const select = screen.getByRole("combobox");
    const options = Array.from(select.querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    expect(options).toEqual(["Руководитель", "Менеджер"]);
  });

  it("админу роль «Админ» доступна", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "admin" } });
    renderSection();
    await userEvent.click(inviteButton()!);

    const select = screen.getByRole("combobox");
    const options = Array.from(select.querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    expect(options).toEqual(["Админ", "Руководитель", "Менеджер"]);
  });
});
