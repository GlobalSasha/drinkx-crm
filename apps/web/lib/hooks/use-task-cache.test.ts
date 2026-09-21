/**
 * One task mutation, every list that shows it (audit G3, BUG-07).
 *
 * The three hook files had drifted apart: the lead-card hooks never
 * invalidated ["tasks"], so closing a task on a lead card left the Задачи page
 * showing it open, and completing one there did not refresh ["my-tasks"]
 * either. These assertions pin the whole set, not one call site.
 */
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { invalidateTaskQueries } from "./use-task-cache";

const LEAD = "lead-1";

function invalidatedKeys(leadId?: string | null): string[] {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  invalidateTaskQueries(qc, leadId);
  return spy.mock.calls.map(([arg]) => JSON.stringify(arg?.queryKey));
}

describe("invalidateTaskQueries", () => {
  it("refreshes every list that can show a task on a lead", () => {
    const keys = invalidatedKeys(LEAD);
    for (const expected of [
      ["tasks"],
      ["my-tasks"],
      ["daily-plan", "today"],
      ["feed", LEAD],
      ["activities", LEAD, "task"],
      ["lead-archive", LEAD],
    ]) {
      expect(keys).toContain(JSON.stringify(expected));
    }
  });

  it("skips the lead-scoped caches for a task without a lead", () => {
    const keys = invalidatedKeys(null);
    expect(keys).toContain(JSON.stringify(["tasks"]));
    expect(keys).toContain(JSON.stringify(["my-tasks"]));
    expect(keys).toContain(JSON.stringify(["daily-plan", "today"]));
    expect(keys.some((k) => k.includes("feed"))).toBe(false);
    expect(keys.some((k) => k.includes("activities"))).toBe(false);
  });

  it("invalidates a filtered Задачи page, not only an exact key", () => {
    // ["tasks"] is a prefix of ["tasks", filters]: the page keeps its filters
    // in the key, and an exact match would leave every filtered view stale.
    const qc = new QueryClient();
    qc.setQueryData(["tasks", { status: "open" }], []);
    invalidateTaskQueries(qc, LEAD);
    const state = qc.getQueryState(["tasks", { status: "open" }]);
    expect(state?.isInvalidated).toBe(true);
  });
});
