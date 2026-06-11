import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { relativeTime } from "./relative-time";

describe("relativeTime", () => {
  const NOW = new Date("2026-06-11T12:00:00.000Z");

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns 'только что' for under a minute", () => {
    expect(relativeTime("2026-06-11T11:59:30.000Z")).toBe("только что");
  });

  it("returns minutes for under an hour", () => {
    expect(relativeTime("2026-06-11T11:45:00.000Z")).toBe("15 мин назад");
  });

  it("returns hours for under a day", () => {
    expect(relativeTime("2026-06-11T09:00:00.000Z")).toBe("3 ч назад");
  });

  it("returns days for older timestamps", () => {
    expect(relativeTime("2026-06-09T12:00:00.000Z")).toBe("2 дн назад");
  });

  it("clamps future timestamps to 'только что'", () => {
    expect(relativeTime("2026-06-11T13:00:00.000Z")).toBe("только что");
  });

  it("returns empty string for an invalid date", () => {
    expect(relativeTime("not-a-date")).toBe("");
  });
});
