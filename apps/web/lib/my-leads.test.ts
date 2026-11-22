import { describe, expect, it } from "vitest";
import { listCallPhone, sortByUrgency, taskLabel, taskUrgency } from "./my-leads";

const now = new Date(2026, 10, 22, 12, 0); // 22 Nov 2026, 12:00 local

function at(y: number, m: number, d: number, h = 10, min = 0) {
  return new Date(y, m, d, h, min).toISOString();
}

describe("taskUrgency / taskLabel", () => {
  it("overdue a few days ago", () => {
    const l = { next_task_due_at: at(2026, 10, 19), has_open_task: true };
    expect(taskUrgency(l, now)).toBe("overdue");
    expect(taskLabel(l, now)).toBe("Просрочено на 3 дн.");
  });
  it("overdue earlier today", () => {
    const l = { next_task_due_at: at(2026, 10, 22, 9, 30), has_open_task: true };
    expect(taskUrgency(l, now)).toBe("overdue");
    expect(taskLabel(l, now)).toBe("Просрочено, 09:30");
  });
  it("later today", () => {
    const l = { next_task_due_at: at(2026, 10, 22, 15, 0), has_open_task: true };
    expect(taskUrgency(l, now)).toBe("today");
    expect(taskLabel(l, now)).toBe("Сегодня, 15:00");
  });
  it("upcoming", () => {
    const l = { next_task_due_at: at(2026, 10, 25), has_open_task: true };
    expect(taskUrgency(l, now)).toBe("upcoming");
    expect(taskLabel(l, now)).toMatch(/^Задача 25 нояб/);
  });
  it("open task without due date vs no task", () => {
    expect(taskLabel({ next_task_due_at: null, has_open_task: true }, now)).toBe("Задача без срока");
    expect(taskLabel({ next_task_due_at: null, has_open_task: false }, now)).toBe("Нет задачи");
  });
});

describe("sortByUrgency", () => {
  it("overdue, today, upcoming by date, no-due, none", () => {
    const leads = [
      { id: "none", next_task_due_at: null, has_open_task: false },
      { id: "later", next_task_due_at: at(2026, 10, 30), has_open_task: true },
      { id: "nodue", next_task_due_at: null, has_open_task: true },
      { id: "today", next_task_due_at: at(2026, 10, 22, 16), has_open_task: true },
      { id: "soon", next_task_due_at: at(2026, 10, 24), has_open_task: true },
      { id: "late2", next_task_due_at: at(2026, 10, 20), has_open_task: true },
      { id: "late5", next_task_due_at: at(2026, 10, 17), has_open_task: true },
    ];
    expect(sortByUrgency(leads, now).map((l) => l.id)).toEqual([
      "late5", "late2", "today", "soon", "later", "nodue", "none",
    ]);
  });
});

describe("listCallPhone", () => {
  it("prefers the primary contact", () => {
    expect(listCallPhone({ primary_contact_phone: "c", phone: "l" })).toBe("c");
    expect(listCallPhone({ primary_contact_phone: null, phone: "l" })).toBe("l");
    expect(listCallPhone({ primary_contact_phone: null, phone: null })).toBeNull();
  });
});
