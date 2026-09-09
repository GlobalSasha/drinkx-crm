import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

// Capture router calls. `vi.hoisted` keeps the spies reachable from the
// hoisted `vi.mock` factory without tripping the top-level-variable trap.
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { TaskTable } from "./TaskTable";
import type { TaskRow } from "@/lib/tasks";

const noop = () => {};

function rowWithLead(): TaskRow {
  return {
    id: "task-1",
    leadId: "lead-1",
    name: "Позвонить клиенту",
    company: "Acme",
    due: null,
    done: false,
    assigneeId: "user-1",
    assigneeName: "Иван",
    authorId: "user-2",
    authorName: "Пётр",
  };
}

function rowWithoutLead(): TaskRow {
  return {
    id: "task-2",
    leadId: null,
    name: "Обновить прайс",
    company: null,
    due: null,
    done: false,
    assigneeId: "user-1",
    assigneeName: "Иван",
    authorId: "user-2",
    authorName: "Пётр",
  };
}

describe("TaskTable", () => {
  afterEach(() => {
    push.mockClear();
  });

  it("clicking a row with a lead pushes /leads/<id>?tab=tasks", async () => {
    render(<TaskTable rows={[rowWithLead()]} onComplete={noop} />);
    await userEvent.click(screen.getByText("Позвонить клиенту"));
    expect(push).toHaveBeenCalledWith("/leads/lead-1?tab=tasks");
  });

  it("clicking a row without a lead does not push and has no role=link", async () => {
    render(<TaskTable rows={[rowWithoutLead()]} onComplete={noop} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Обновить прайс"));
    expect(push).not.toHaveBeenCalled();
  });

  it("clicking the checkbox calls onComplete with the row", async () => {
    const onComplete = vi.fn();
    const row = rowWithLead();
    render(<TaskTable rows={[row]} onComplete={onComplete} />);
    await userEvent.click(screen.getByRole("button", { name: "Отметить выполненной" }));
    expect(onComplete).toHaveBeenCalledWith(row);
    expect(push).not.toHaveBeenCalled();
  });
});
