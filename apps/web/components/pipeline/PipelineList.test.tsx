import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { PipelineList } from "./PipelineList";
import type { LeadListItem, Stage } from "@/lib/types";

const stages = [
  { id: "s1", name: "Новый", color: "#999", position: 0 },
  { id: "s2", name: "КП", color: "#f60", position: 1 },
] as unknown as Stage[];

function lead(id: string, over: Partial<LeadListItem>): LeadListItem {
  return {
    id,
    company_name: id,
    stage_id: "s1",
    segment: null,
    city: null,
    priority: null,
    phone: null,
    primary_contact_phone: null,
    next_task_due_at: null,
    has_open_task: false,
    ...over,
  } as unknown as LeadListItem;
}

const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString();

describe("PipelineList — «Мои лиды» на телефоне", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(cleanup);

  it("«Срочные»: сначала просроченные, лиды без задачи в конце", () => {
    render(
      <PipelineList
        stages={stages}
        leads={[
          lead("Без задачи", {}),
          lead("Через неделю", { next_task_due_at: day(7), has_open_task: true }),
          lead("Просрочен", { next_task_due_at: day(-3), has_open_task: true, stage_id: "s2" }),
        ]}
      />,
    );
    const names = screen.getAllByRole("link", { name: /Без задачи|Через неделю|Просрочен/ })
      .map((a) => a.textContent ?? "");
    expect(names[0]).toMatch(/^Просрочен/);
    expect(names[2]).toMatch(/^Без задачи/);
    expect(screen.getByText("Просрочено на 3 дн.")).toBeTruthy();
    expect(screen.getByText("Нет задачи")).toBeTruthy();
  });

  it("кнопка звонка — на телефон основного контакта", () => {
    render(
      <PipelineList
        stages={stages}
        leads={[lead("Кофейня", { phone: "+7 1", primary_contact_phone: "+7 2" })]}
      />,
    );
    const call = screen.getByRole("link", { name: "Позвонить: Кофейня" });
    expect(call.getAttribute("href")).toBe("tel:+7 2");
  });

  it("фильтр по этапу работает и в «Срочных», вид запоминается", () => {
    render(
      <PipelineList
        stages={stages}
        leads={[lead("A", {}), lead("B", { stage_id: "s2" })]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /КП/ }));
    expect(screen.queryByRole("link", { name: /^A/ })).toBeNull();
    expect(screen.getByRole("link", { name: /^B/ })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "По этапам" }));
    expect(window.localStorage.getItem("drinkx:my-leads-view")).toBe("stages");
    expect(within(screen.getByRole("heading", { name: "КП" }).parentElement!).getByText("1")).toBeTruthy();
  });
});
