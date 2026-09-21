import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { NeedsReviewRow } from "./NeedsReviewRow";
import type { LeadListItem } from "@/lib/types";

function lead(ai_confidence: number | null): LeadListItem {
  return {
    id: "lead-1",
    company_name: "Acme",
    needs_review: true,
    ai_confidence,
  } as unknown as LeadListItem;
}

function renderRow(item: LeadListItem) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <NeedsReviewRow lead={item} />
    </QueryClientProvider>,
  );
}

describe("NeedsReviewRow — бейдж «AI создал»", () => {
  it("показывает реальную уверенность из ai_confidence", () => {
    // Регрессия ARCH-03 DRIFT-1: бейдж читал ai_data, которого в списочном
    // ответе нет, и показывал 0% на каждой карточке.
    renderRow(lead(0.85));
    expect(screen.getByText("AI создал · 85%")).toBeInTheDocument();
  });

  it("без уверенности не выдумывает ноль", () => {
    renderRow(lead(null));
    expect(screen.getByText("AI создал")).toBeInTheDocument();
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
  });
});
