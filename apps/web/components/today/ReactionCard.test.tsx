import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CompanyInflow } from "@/lib/types";

const data = {
  timezone: "Europe/Moscow",
  today: "2026-10-29",
  days: [],
  months: [],
  sources: [],
  reaction: {
    current: { total: 10, touched: 4, median_hours: 3, within_hour: 1 },
    previous: { total: 8, touched: 5, median_hours: 6, within_hour: 2 },
    waiting_count: 6,
    waiting: [{ lead_id: "l1", company_name: "Кофейня у дома", source: "Сайт", hours: 75 }],
  },
} satisfies CompanyInflow;

vi.mock("@/lib/hooks/use-company", () => ({
  useCompanyInflow: () => ({ data, isLoading: false, isError: false }),
}));

import { ReactionCard, formatWait } from "./ReactionCard";

describe("formatWait", () => {
  it("reads naturally at every scale", () => {
    expect(formatWait(0.25)).toBe("15 мин");
    expect(formatWait(5.4)).toBe("5 ч");
    expect(formatWait(75)).toBe("3 дн.");
  });
});

describe("ReactionCard", () => {
  it("shows the median, the share answered and the oldest waiting lead", () => {
    render(<ReactionCard />);
    expect(screen.getByText("3 ч")).toBeInTheDocument();
    expect(screen.getByText("-50%")).toBeInTheDocument(); // twice as fast as before
    expect(screen.getByText("40% заявок")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Кофейня у дома/ })).toHaveAttribute("href", "/leads/l1");
    expect(screen.getByText("Показаны самые старые 1 из 6.")).toBeInTheDocument();
  });
});
