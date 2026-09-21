/**
 * Счётчики фасетов базы лидов обязаны обновляться вместе со списком
 * (ARCH-03 DRIFT-3).
 *
 * `usePoolFacets` считает «Москва (12)» на сервере и держит ответ минуту.
 * Каждое действие, выводящее карточки из пула, сбрасывало `["leads-pool"]`
 * и не трогало `["leads-pool-facets"]` — список пустел сразу, а подпись у
 * фильтра ещё до минуты обещала двенадцать карточек. Оба числа на одном
 * экране и оба «серверные».
 *
 * Проверяется через настоящие хуки и настоящий QueryClient: замокан только
 * HTTP-слой.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, api: { ...actual.api, post: apiPost } };
});

import {
  POOL_FACETS_KEY,
  useAssignLeads,
  useClaimLead,
  useCreateSprint,
  useUnclaimLead,
} from "./use-leads";

function setup() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

function invalidatedKeys(spy: { mock: { calls: unknown[][] } }): string[] {
  return spy.mock.calls.map(([arg]) =>
    JSON.stringify((arg as { queryKey?: unknown } | undefined)?.queryKey),
  );
}

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ id: "lead-1", assigned_count: 1, claimed_count: 1 });
});

describe.each([
  ["взять карточку себе", useClaimLead, "lead-1"],
  ["вернуть карточку в базу", useUnclaimLead, "lead-1"],
  ["выдать менеджеру", useAssignLeads, { to_user_id: "u-1", mode: "filter" as const, limit: 5 }],
  ["набрать спринт", useCreateSprint, { limit: 5 }],
])("%s", (_label, hook, variables) => {
  it("сбрасывает и счётчики фасетов, не только список", async () => {
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => (hook as () => ReturnType<typeof useClaimLead>)(), {
      wrapper,
    });

    (result.current.mutate as (v: unknown) => void)(variables);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // onSettled у claim отрабатывает после isSuccess.
    await waitFor(() =>
      expect(invalidatedKeys(spy)).toContain(JSON.stringify([...POOL_FACETS_KEY])),
    );
  });
});
