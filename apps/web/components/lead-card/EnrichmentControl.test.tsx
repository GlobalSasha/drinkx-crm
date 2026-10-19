import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const { latest, trigger } = vi.hoisted(() => ({ latest: vi.fn(), trigger: vi.fn() }));
vi.mock("@/lib/hooks/use-enrichment", () => ({ useLatestEnrichment: latest, useTriggerEnrichment: trigger }));
import { EnrichmentControl } from "./EnrichmentControl";

const mutate = vi.fn();
beforeEach(() => {
  mutate.mockReset();
  latest.mockReturnValue({ data: null, isPending: false, isError: false });
  trigger.mockReturnValue({ mutate, isPending: false, error: null });
});

describe("AI в карточке", () => {
  it("запускает дополнение без перезаписи", () => {
    render(<EnrichmentControl leadId="lead-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Дополнить через AI" }));
    expect(mutate).toHaveBeenCalledWith("append");
  });
  it("не разрешает второй запуск и показывает процесс", () => {
    latest.mockReturnValue({ data: { status: "running" } });
    render(<EnrichmentControl leadId="lead-1" />);
    expect(screen.getByRole("button", { name: "AI ищет сведения…" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("обновится автоматически");
  });
  it("после ошибки позволяет повторить и не обещает успех", () => {
    latest.mockReturnValue({ data: { status: "failed" } });
    render(<EnrichmentControl leadId="lead-1" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Прежние сведения сохранены");
    expect(screen.getByRole("button", { name: "Дополнить через AI" })).toBeEnabled();
  });
  it("при недоступном статусе сначала предлагает проверить его", () => {
    const refetch = vi.fn();
    latest.mockReturnValue({ isError: true, refetch });
    render(<EnrichmentControl leadId="lead-1" />);
    expect(screen.getByRole("button", { name: "Дополнить через AI" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Обновить статус" }));
    expect(refetch).toHaveBeenCalledOnce();
  });
});
