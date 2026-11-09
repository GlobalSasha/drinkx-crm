import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UserSelect } from "./UserSelect";

const users = [
  { id: "kirill", name: "Кирилл", role: "head" },
  { id: "dima", name: "Дмитрий", role: "manager" },
  { id: "vlada", name: "Влада", role: "manager" },
] as never;

function options() {
  return screen.getAllByRole("option").map((o) => o.textContent);
}

describe("UserSelect: пометка для чужого лида", () => {
  it("помечает менеджера, которому лид не принадлежит", () => {
    render(<UserSelect value={null} onChange={() => {}} users={users} allowEmpty leadOwnerId="vlada" />);
    expect(options()).toEqual([
      "— не выбран —",
      "Кирилл · Руководитель",
      "Дмитрий · Менеджер · не видит карточку",
      "Влада · Менеджер",
    ]);
  });

  it("лид в базе без владельца не видит ни один менеджер", () => {
    render(<UserSelect value={null} onChange={() => {}} users={users} allowEmpty leadOwnerId={null} />);
    expect(options().filter((o) => o?.includes("не видит"))).toHaveLength(2);
  });

  it("без лида пометок нет", () => {
    render(<UserSelect value={null} onChange={() => {}} users={users} allowEmpty />);
    expect(options().some((o) => o?.includes("не видит"))).toBe(false);
  });
});
