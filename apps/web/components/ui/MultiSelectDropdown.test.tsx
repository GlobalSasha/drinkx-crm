import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MultiSelectDropdown } from "./MultiSelectDropdown";

// На телефоне фильтр у правого края раскрывал список за экран, и страница
// становилась шире экрана. Список должен открываться в сторону, где есть место.

function mockMenuRect(left: number, right: number) {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
    function (this: HTMLElement) {
      if (this.getAttribute("role") === "listbox") {
        return { left, right, top: 0, bottom: 100, width: right - left, height: 100, x: left, y: 0, toJSON: () => ({}) } as DOMRect;
      }
      return { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
    },
  );
}

async function openMenu(align?: "left" | "right") {
  render(
    <MultiSelectDropdown label="Бренд" options={["AeroMilk", "DrinkX"]} selected={[]} onChange={() => {}} align={align} />,
  );
  await userEvent.click(screen.getByRole("button", { name: /Бренд/ }));
  return screen.getByRole("listbox");
}

describe("MultiSelectDropdown: край экрана", () => {
  afterEach(() => vi.restoreAllMocks());

  it("открывается влево от кнопки, если места справа нет", async () => {
    window.innerWidth = 375;
    mockMenuRect(209, 433);
    const menu = await openMenu();
    expect(menu.className).toContain("right-0");
    expect(menu.className).not.toContain("left-0");
  });

  it("остаётся слева, если помещается", async () => {
    window.innerWidth = 375;
    mockMenuRect(16, 240);
    const menu = await openMenu();
    expect(menu.className).toContain("left-0");
  });

  it("меню с выравниванием вправо переворачивается, если упирается в левый край", async () => {
    window.innerWidth = 375;
    mockMenuRect(-40, 184);
    const menu = await openMenu("right");
    expect(menu.className).toContain("left-0");
  });
});
