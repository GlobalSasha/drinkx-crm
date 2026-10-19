import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
vi.mock("@/lib/api-client", () => ({ api: { get: vi.fn() }, ApiError: class extends Error {} }));
import { useLatestEnrichment } from "./use-enrichment";

function setup(initial: unknown) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(["enrichment", "lead-1", "latest"], initial);
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  renderHook(() => useLatestEnrichment("lead-1"), {
    wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>,
  });
  return { qc, invalidate };
}

describe("Обновление карточки после AI", () => {
  it.each(["succeeded", "failed"])("обновляет карточку и историю при running → %s", async (status) => {
    const { qc, invalidate } = setup({ id: "run-1", status: "running" });
    act(() => { qc.setQueryData(["enrichment", "lead-1", "latest"], { id: "run-1", status }); });
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["lead", "lead-1"] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["feed", "lead-1"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["contacts", "lead-1"] });
    qc.clear();
  });
  it("обновляет быстрый запуск, завершившийся до первого опроса", async () => {
    const { qc, invalidate } = setup(null);
    act(() => { qc.setQueryData(["enrichment", "lead-1", "latest"], { id: "new-run", status: "succeeded" }); });
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["lead", "lead-1"] }));
    qc.clear();
  });
  it("старый завершённый запуск при открытии не запускает обновления", () => {
    const { qc, invalidate } = setup({ id: "old-run", status: "succeeded" });
    expect(invalidate).not.toHaveBeenCalled();
    qc.clear();
  });
});
