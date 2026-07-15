import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

// Capture router calls. `vi.hoisted` keeps the spies reachable from the
// hoisted `vi.mock` factory without tripping the top-level-variable trap.
const { back, push } = vi.hoisted(() => ({ back: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ back, push }) }));

import { LeadCardHeader } from "./LeadCardHeader";
import type { LeadOut, Stage } from "@/lib/types";

// jsdom lacks ResizeObserver, which Radix's Dropdown primitives touch.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??=
  ResizeObserverStub;

const lead = {
  id: "lead-1",
  company_name: "Acme",
  priority: "A",
  priority_label: "Высокий",
  segment: null,
  assignment_status: "assigned",
  assigned_to: "someone-else",
  stage_id: "stage-1",
  primary_contact_name: null,
  assigned_at: null,
  created_at: "2026-01-01T00:00:00Z",
  last_activity_at: null,
  is_rotting_stage: false,
  is_rotting_next_step: false,
  source_form_id: null,
  source_form_name: null,
  source: null,
} as unknown as LeadOut;

const noop = () => {};

function renderHeader() {
  render(
    <LeadCardHeader
      lead={lead}
      stages={[] as Stage[]}
      displayStage={undefined}
      meId="me"
      mergedFromCount={0}
      isClosed={false}
      isWon={false}
      isLost={false}
      closedAt={null}
      wonStage={null}
      lostStageRef={null}
      claimPending={false}
      unclaimPending={false}
      onClaim={noop}
      onReturnToPool={noop}
      onTransfer={noop}
      onCloseWon={noop}
      onCloseLost={noop}
      onFindDuplicates={noop}
      onDelete={noop}
      onStageSelect={noop}
      onRename={noop}
    />,
  );
}

function setHistoryLength(n: number) {
  Object.defineProperty(window.history, "length", {
    value: n,
    configurable: true,
  });
}

describe("LeadCardHeader — back button", () => {
  afterEach(() => {
    back.mockClear();
    push.mockClear();
  });

  it("pops in-app history when the user navigated in (e.g. from a manager's pipeline)", async () => {
    setHistoryLength(3);
    renderHeader();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(back).toHaveBeenCalledTimes(1);
    expect(push).not.toHaveBeenCalled();
  });

  it("falls back to /pipeline when the lead was opened directly (no in-app history)", async () => {
    setHistoryLength(1);
    renderHeader();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(push).toHaveBeenCalledWith("/pipeline");
    expect(back).not.toHaveBeenCalled();
  });
});
