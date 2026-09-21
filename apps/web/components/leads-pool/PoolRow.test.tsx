import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

// Capture router calls. `vi.hoisted` keeps the spies reachable from the
// hoisted `vi.mock` factory without tripping the top-level-variable trap.
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { PoolRow } from "./PoolRow";
import type { LeadListItem } from "@/lib/types";

const lead = {
  id: "lead-1",
  company_name: "Acme",
  city: null,
  segment: null,
  score: 0,
  fit_score: null,
  assignment_status: "pool",
  source_form_name: null,
  needs_review: false,
  ai_confidence: null,
} as unknown as LeadListItem;

const noop = () => {};

function renderInTable(ui: React.ReactElement) {
  return render(
    <table>
      <tbody>{ui}</tbody>
    </table>,
  );
}

describe("PoolRow", () => {
  afterEach(() => {
    push.mockClear();
  });

  it("не рендерит чекбокс без selectable", () => {
    renderInTable(<PoolRow lead={lead} onClaim={noop} claiming={false} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("с selectable клик по чекбоксу зовёт onToggleSelect и не открывает карточку", async () => {
    const onToggleSelect = vi.fn();
    renderInTable(
      <PoolRow
        lead={lead}
        onClaim={noop}
        claiming={false}
        selectable
        selected={false}
        onToggleSelect={onToggleSelect}
      />,
    );
    const checkbox = screen.getByRole("checkbox", { name: "Выбрать Acme" });
    const tapTarget = checkbox.closest("label");
    expect(tapTarget).not.toBeNull();
    await userEvent.click(tapTarget!);
    expect(onToggleSelect).toHaveBeenCalledWith("lead-1");
    expect(push).not.toHaveBeenCalled();
  });

  it("клик по названию компании зовёт router.push с карточкой лида", async () => {
    renderInTable(<PoolRow lead={lead} onClaim={noop} claiming={false} />);
    await userEvent.click(screen.getByText("Acme"));
    expect(push).toHaveBeenCalledWith("/leads/lead-1");
  });
});
