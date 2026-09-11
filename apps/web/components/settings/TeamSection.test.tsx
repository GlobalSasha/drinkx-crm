import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

// Кто приглашает: админ и руководитель — да, менеджер — нет.
// Роль «Админ» в списке видит только админ (сервер откажет в любом случае,
// селект просто не предлагает заведомо мёртвый вариант).

const { meMock, inviteMock } = vi.hoisted(() => ({
  meMock: vi.fn(),
  inviteMock: vi.fn(),
}));
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
  useInviteUser: () => ({ mutate: inviteMock, isPending: false }),
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
    inviteMock.mockReset();
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

  it("говорит про уже существующий аккаунт, а не про обычное приглашение", async () => {
    // Человек пробовал войти до приглашения — аккаунт в Supabase уже есть.
    // Это не отказ: доступ открыт, ему ушла ссылка для входа.
    meMock.mockReturnValue({ data: { id: "me-1", role: "admin" } });
    inviteMock.mockImplementation((_body, opts) =>
      opts.onSuccess({ id: "i1", email_outcome: "sign_in_link" }),
    );
    renderSection();

    await userEvent.click(inviteButton()!);
    await userEvent.type(
      screen.getByPlaceholderText("manager@drinkx.tech"),
      "kirill@drinkx.tech",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Отправить приглашение" }),
    );

    expect(screen.getByText("Письмо отправлено")).toBeInTheDocument();
    expect(screen.getByText(/уже был аккаунт/)).toBeInTheDocument();
  });
});
