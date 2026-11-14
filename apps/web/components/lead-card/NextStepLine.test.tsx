import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { tasksMock } = vi.hoisted(() => ({ tasksMock: vi.fn() }));
vi.mock("@/lib/hooks/use-lead-tasks", () => ({ useLeadTasks: () => tasksMock() }));

import { NextStepLine, describeDue } from "./NextStepLine";
import type { MyTaskOut } from "@/lib/types";

function task(over: Partial<MyTaskOut> = {}): MyTaskOut {
  return {
    id: "t1",
    lead_id: "l1",
    lead_company_name: "Кофейня",
    text: "Отправить КП",
    task_due_at: null,
    task_done: false,
    task_completed_at: null,
    created_at: "2026-11-10T09:00:00Z",
    assignee_user_id: "owner",
    assignee_name: "Дмитрий",
    explicit_assignee_user_id: null,
    author_user_id: "owner",
    author_name: "Дмитрий",
    ...over,
  };
}

function loaded(items: MyTaskOut[], open = items.filter((t) => !t.task_done).length) {
  tasksMock.mockReturnValue({
    items,
    counts: { total: items.length, open, done: items.length - open, overdue: 0 },
    isPending: false,
    isError: false,
  });
}

const plan = vi.fn();
beforeEach(() => {
  tasksMock.mockReset();
  plan.mockReset();
});

function renderLine() {
  return render(<NextStepLine leadId="l1" ownerId="owner" onPlanTask={plan} />);
}

describe("describeDue", () => {
  const now = new Date(2026, 10, 13, 12, 0); // 13.11.2026 12:00
  it("без срока", () => {
    expect(describeDue(null, now)).toEqual({ label: "без срока", overdue: false });
  });
  it("сегодня, завтра и дата", () => {
    expect(describeDue(new Date(2026, 10, 13, 18, 0).toISOString(), now).label).toBe("сегодня");
    expect(describeDue(new Date(2026, 10, 14, 18, 0).toISOString(), now).label).toBe("завтра");
    expect(describeDue(new Date(2026, 10, 17, 18, 0).toISOString(), now).label).toBe("до 17.11");
  });
  it("просрочка в днях с правильным склонением", () => {
    expect(describeDue(new Date(2026, 10, 13, 9, 0).toISOString(), now)).toEqual({
      label: "просрочено сегодня",
      overdue: true,
    });
    expect(describeDue(new Date(2026, 10, 12, 18, 0).toISOString(), now).label).toBe("просрочено на 1 день");
    expect(describeDue(new Date(2026, 10, 10, 18, 0).toISOString(), now).label).toBe("просрочено на 3 дня");
    expect(describeDue(new Date(2026, 10, 1, 18, 0).toISOString(), now).label).toBe("просрочено на 12 дней");
  });
});

describe("NextStepLine", () => {
  it("показывает ближайшую открытую задачу и сколько ещё", () => {
    loaded([task(), task({ id: "t2", text: "Позвонить" }), task({ id: "t3", text: "Опрос" })]);
    renderLine();
    expect(screen.getByText("Что дальше")).toBeInTheDocument();
    expect(screen.getByText("Отправить КП")).toBeInTheDocument();
    expect(screen.getByText("без срока")).toBeInTheDocument();
    expect(screen.getByText("ещё 2")).toBeInTheDocument();
    expect(screen.queryByText("Позвонить")).not.toBeInTheDocument();
  });

  it("не пишет «ещё», если задача одна", () => {
    loaded([task()]);
    renderLine();
    expect(screen.queryByText(/^ещё/)).not.toBeInTheDocument();
  });

  it("называет исполнителя, только если задача не у владельца", () => {
    loaded([task({ assignee_user_id: "head", assignee_name: "Кирилл" })]);
    renderLine();
    expect(screen.getByText("Кирилл")).toBeInTheDocument();
  });

  it("не называет владельца лишний раз", () => {
    loaded([task()]);
    renderLine();
    expect(screen.queryByText("Дмитрий")).not.toBeInTheDocument();
  });

  it("без открытых задач — предупреждение и кнопка", () => {
    loaded([task({ task_done: true })], 0);
    renderLine();
    expect(screen.getByText("Нет следующего шага")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Поставить задачу" }));
    expect(plan).toHaveBeenCalledTimes(1);
  });

  it("пустой список — тоже нет шага", () => {
    loaded([], 0);
    renderLine();
    expect(screen.getByText("Нет следующего шага")).toBeInTheDocument();
  });

  it("пока грузится или при ошибке — ничего не показывает", () => {
    tasksMock.mockReturnValue({ items: [], counts: undefined, isPending: true, isError: false });
    const { container, rerender } = renderLine();
    expect(container).toBeEmptyDOMElement();
    tasksMock.mockReturnValue({ items: [], counts: undefined, isPending: false, isError: true });
    rerender(<NextStepLine leadId="l1" ownerId="owner" onPlanTask={plan} />);
    expect(container).toBeEmptyDOMElement();
  });
});
