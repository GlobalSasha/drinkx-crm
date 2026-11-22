import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MobileActionBar, pickCallPhone } from "./MobileActionBar";
import type { LeadOut, Stage } from "@/lib/types";

const contacts = { data: [] as { id: string; phone: string | null }[] };
vi.mock("@/lib/hooks/use-contacts", () => ({ useContacts: () => contacts }));

const lead = { id: "l1", phone: "+7 900 000-00-00", primary_contact_id: null } as unknown as LeadOut;
const stages = [
  { id: "s1", name: "Новый", is_won: false, is_lost: false },
  { id: "s2", name: "Выиграно", is_won: true, is_lost: false },
] as unknown as Stage[];

function renderBar(over: Partial<Parameters<typeof MobileActionBar>[0]> = {}) {
  const props = {
    lead,
    stages,
    currentStageId: "s1",
    onComment: vi.fn(),
    onTask: vi.fn(),
    onStageSelect: vi.fn(),
    ...over,
  };
  render(<MobileActionBar {...props} />);
  return props;
}

describe("pickCallPhone", () => {
  it("prefers the primary contact, falls back to the lead phone", () => {
    const l = { phone: "lead-phone", primary_contact_id: "c2" };
    const cs = [
      { id: "c1", phone: "first" },
      { id: "c2", phone: "primary" },
    ];
    expect(pickCallPhone(l, cs)).toBe("primary");
    expect(pickCallPhone({ ...l, primary_contact_id: null }, cs)).toBe("first");
    expect(pickCallPhone(l, [])).toBe("lead-phone");
    expect(pickCallPhone({ phone: null, primary_contact_id: null }, [])).toBeNull();
  });
});

describe("MobileActionBar", () => {
  afterEach(cleanup);

  it("«Позвонить» — ссылка tel: на телефон лида", () => {
    renderBar();
    const link = screen.getByRole("link", { name: /Позвонить/ });
    expect(link.getAttribute("href")).toBe("tel:+7 900 000-00-00");
  });

  it("без телефона «Позвонить» неактивна", () => {
    renderBar({ lead: { ...lead, phone: null } as LeadOut });
    expect(screen.getByRole("button", { name: /Позвонить/ })).toHaveProperty("disabled", true);
  });

  it("«Комментарий» и «Задача» вызывают свои обработчики", () => {
    const p = renderBar();
    fireEvent.click(screen.getByRole("button", { name: /Комментарий/ }));
    fireEvent.click(screen.getByRole("button", { name: /Задача/ }));
    expect(p.onComment).toHaveBeenCalledOnce();
    expect(p.onTask).toHaveBeenCalledOnce();
  });

  it("прячется, пока менеджер печатает в поле, и возвращается после", () => {
    render(
      <>
        <textarea aria-label="поле" />
        <MobileActionBar
          lead={lead}
          stages={stages}
          currentStageId="s1"
          onComment={vi.fn()}
          onTask={vi.fn()}
          onStageSelect={vi.fn()}
        />
      </>,
    );
    const box = screen.getByLabelText("поле");
    fireEvent.focusIn(box);
    expect(screen.queryByRole("navigation", { name: "Действия с лидом" })).toBeNull();
    fireEvent.focusOut(box);
    expect(screen.getByRole("navigation", { name: "Действия с лидом" })).toBeTruthy();
  });
});
