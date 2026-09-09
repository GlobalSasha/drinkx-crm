import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UserSelect } from "./UserSelect";
import type { UserListItemOut } from "@/lib/types";

const users: UserListItemOut[] = [
  { id: "u1", email: "anna@drinkx.tech", name: "Анна", role: "admin", last_login_at: null },
  { id: "u2", email: "boris@drinkx.tech", name: "Борис", role: "head", last_login_at: null },
  { id: "u3", email: "vera@drinkx.tech", name: "", role: "manager", last_login_at: null },
];

describe("UserSelect", () => {
  it("без allowEmpty показывает плейсхолдер при пустом value", () => {
    render(<UserSelect value={null} onChange={vi.fn()} users={users} />);

    const select = screen.getByRole("combobox");
    const placeholder = select.querySelector<HTMLOptionElement>('option[value=""]');
    expect(select).toHaveValue("");
    expect(placeholder).toBeDisabled();
    expect(placeholder).toHaveAttribute("hidden");
  });

  it("рендерит пользователей с подписями ролей и «(вы)»", () => {
    render(
      <UserSelect value={null} onChange={vi.fn()} users={users} meId="u2" />,
    );
    expect(screen.getByRole("option", { name: "Анна · Админ" })).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Борис · Руководитель (вы)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "vera@drinkx.tech · Менеджер" }),
    ).toBeInTheDocument();
  });

  it("выбор опции вызывает onChange с id", async () => {
    const onChange = vi.fn();
    render(<UserSelect value={null} onChange={onChange} users={users} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "u1");
    expect(onChange).toHaveBeenCalledWith("u1");
  });

  it("при allowEmpty выбор пустой опции вызывает onChange(null)", async () => {
    const onChange = vi.fn();
    render(
      <UserSelect
        value="u1"
        onChange={onChange}
        users={users}
        allowEmpty
        emptyLabel="— не выбран —"
      />,
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "— не выбран —");
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
