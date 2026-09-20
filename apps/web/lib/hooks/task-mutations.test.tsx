/**
 * Every task mutation must refresh every list (audit G3, BUG-07).
 *
 * The previous test pins the helper. This one pins the wiring: that each
 * mutation actually calls it, through the real hooks and a real QueryClient,
 * with only the HTTP boundary mocked. Before the fix the lead-card hooks
 * invalidated their own sets and never touched ["tasks"].
 */
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";

const { apiPost, apiDelete, apiPatch } = vi.hoisted(() => ({
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
}));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { ...actual.api, post: apiPost, delete: apiDelete, patch: apiPatch },
  };
});

import {
  useCreateLeadTask,
  useCompleteLeadTask,
  useReopenLeadTask,
  useArchiveLeadTask,
  useRestoreLeadTask,
} from "./use-lead-tasks";
import { useCreateTask, useUpdateTask } from "./use-tasks";
import { useCompleteMyTask, useReopenMyTask } from "./use-my-tasks";

const LEAD = "lead-1";

const EXPECTED_WITH_LEAD = [
  ["tasks"],
  ["my-tasks"],
  ["daily-plan", "today"],
  ["feed", LEAD],
  ["activities", LEAD, "task"],
];

function setup() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, spy, wrapper };
}

type InvalidateSpy = { mock: { calls: unknown[][] } };

function keysOf(spy: InvalidateSpy): string[] {
  return spy.mock.calls.map(([arg]) =>
    JSON.stringify((arg as { queryKey?: unknown } | undefined)?.queryKey),
  );
}

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ id: "t1", lead_id: LEAD });
  apiDelete.mockReset().mockResolvedValue({ id: "t1", lead_id: LEAD });
  apiPatch.mockReset().mockResolvedValue({ id: "t1", lead_id: LEAD });
});

describe.each([
  ["create from the lead card", useCreateLeadTask, { text: "Позвонить" }],
  ["complete from the lead card", useCompleteLeadTask, "act-1"],
  ["reopen from the lead card", useReopenLeadTask, "act-1"],
  ["archive from the lead card", useArchiveLeadTask, "act-1"],
  ["restore from the lead card", useRestoreLeadTask, "act-1"],
])("%s", (_label, hook, variables) => {
  it("refreshes every list that shows the task", async () => {
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => (hook as (id: string) => ReturnType<typeof useCompleteLeadTask>)(LEAD), { wrapper });

    (result.current.mutate as (v: unknown) => void)(variables);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysOf(spy);
    for (const expected of EXPECTED_WITH_LEAD) {
      expect(keys, `missing ${JSON.stringify(expected)}`).toContain(JSON.stringify(expected));
    }
  });
});

describe("delegating through PATCH /tasks/{id}", () => {
  it("refreshes every list that shows the task", async () => {
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useUpdateTask(), { wrapper });

    result.current.mutate({ taskId: "t1", body: { assignee_user_id: null }, leadId: LEAD });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysOf(spy);
    for (const expected of EXPECTED_WITH_LEAD) {
      expect(keys, `missing ${JSON.stringify(expected)}`).toContain(JSON.stringify(expected));
    }
  });

  it("sends an explicit null so the server can tell it from an omitted field", async () => {
    const { wrapper } = setup();
    const { result } = renderHook(() => useUpdateTask(), { wrapper });

    result.current.mutate({ taskId: "t1", body: { assignee_user_id: null }, leadId: LEAD });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const [, body] = apiPatch.mock.calls[0];
    expect(body).toHaveProperty("assignee_user_id", null);
  });
});

describe.each([
  ["complete from the Задачи page", useCompleteMyTask],
  ["reopen from the Задачи page", useReopenMyTask],
])("%s", (_label, hook) => {
  it("refreshes every list that shows the task", async () => {
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => hook(), { wrapper });

    result.current.mutate({ leadId: LEAD, taskId: "t1" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysOf(spy);
    for (const expected of EXPECTED_WITH_LEAD) {
      expect(keys, `missing ${JSON.stringify(expected)}`).toContain(JSON.stringify(expected));
    }
  });
});

describe("a standalone task", () => {
  it("refreshes the cross-lead lists and nothing lead-scoped", async () => {
    apiPost.mockResolvedValue({ id: "t1", lead_id: null });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useCreateTask(), { wrapper });

    result.current.mutate({ text: "Без лида" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysOf(spy);
    expect(keys).toContain(JSON.stringify(["tasks"]));
    expect(keys).toContain(JSON.stringify(["my-tasks"]));
    expect(keys.some((k) => k.includes("feed"))).toBe(false);
  });
});
