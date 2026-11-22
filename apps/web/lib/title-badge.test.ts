import { describe, expect, it } from "vitest";
import { withUnreadPrefix } from "./title-badge";

describe("withUnreadPrefix", () => {
  it("adds the unread count", () => {
    expect(withUnreadPrefix("DrinkX CRM", 3)).toBe("(3) DrinkX CRM");
  });

  it("returns the bare title for zero", () => {
    expect(withUnreadPrefix("(3) DrinkX CRM", 0)).toBe("DrinkX CRM");
  });

  it("replaces an existing prefix instead of stacking", () => {
    expect(withUnreadPrefix("(3) DrinkX CRM", 5)).toBe("(5) DrinkX CRM");
  });

  it("caps large counts", () => {
    expect(withUnreadPrefix("DrinkX CRM", 250)).toBe("(99+) DrinkX CRM");
    expect(withUnreadPrefix("(99+) DrinkX CRM", 2)).toBe("(2) DrinkX CRM");
  });
});
