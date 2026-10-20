import { describe, expect, it } from "vitest";
import { dayPart, headSummary, managerSummary } from "./today-summary";

describe("dayPart", () => {
  it("splits the day at 5, 12 and 18", () => {
    expect(dayPart(4)).toBe("night");
    expect(dayPart(5)).toBe("morning");
    expect(dayPart(12)).toBe("day");
    expect(dayPart(18)).toBe("evening");
  });
});

describe("managerSummary", () => {
  const focus = { id: "l1", name: "Сеть Малина Саратов" };

  it("lists today's work and where to start", () => {
    expect(
      managerSummary({ dueToday: 6, overdue: 2, rotting: 3, focus }, "morning"),
    ).toBe("На сегодня 6 задач, 2 просрочены, 3 лида протухают. Начните с «Сеть Малина Саратов».");
  });

  it("names the noun when there is nothing due today", () => {
    expect(managerSummary({ dueToday: 0, overdue: 1, rotting: 0, focus }, "day")).toBe(
      "1 задача просрочена. Начните с «Сеть Малина Саратов».",
    );
  });

  it("is calm when nothing burns", () => {
    expect(managerSummary({ dueToday: 0, overdue: 0, rotting: 0, focus: null }, "morning")).toBe(
      "На сегодня всё спокойно: просрочек нет, протухающих лидов нет.",
    );
  });

  it("counts what is left in the evening", () => {
    expect(managerSummary({ dueToday: 1, overdue: 1, rotting: 5, focus }, "evening")).toBe(
      "Осталось 2 задачи — закройте или перенесите на завтра.",
    );
  });

  it("points to tomorrow when the day is closed", () => {
    expect(managerSummary({ dueToday: 0, overdue: 0, rotting: 1, focus }, "evening")).toBe(
      "Задачи на сегодня закрыты. Завтра начните с «Сеть Малина Саратов».",
    );
  });
});

describe("headSummary", () => {
  it("combines leads, stuck deals and a silent manager", () => {
    expect(
      headSummary({ leadsToday: 5, leadsYesterday: 14, stuck: 6, silent: { name: "Игорь", days: 2 } }),
    ).toBe("Сегодня 5 новых заявок (вчера 14). 6 сделок застряли больше 7 дней. Игорь не заходит 2 дня.");
  });

  it("skips what is unknown or zero", () => {
    expect(headSummary({ leadsToday: 1, leadsYesterday: null, stuck: 0, silent: null })).toBe(
      "Сегодня 1 новая заявка.",
    );
    expect(headSummary({ leadsToday: null, leadsYesterday: null, stuck: null, silent: null })).toBe(
      "Команда на месте, срочного нет.",
    );
  });
});
