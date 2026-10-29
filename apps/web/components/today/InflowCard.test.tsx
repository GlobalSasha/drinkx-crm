import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CompanyInflow } from "@/lib/types";

const data: CompanyInflow = {
  timezone: "Europe/Moscow",
  today: "2026-10-29",
  days: [
    { bucket: "2026-10-29", source: "Сайт", count: 2 },
    { bucket: "2026-10-29", source: "Вручную и загрузка базы", count: 80 },
    { bucket: "2026-10-28", source: "Сайт", count: 1 },
  ],
  months: [
    { bucket: "2026-10-01", source: "Сайт", count: 3 },
    { bucket: "2026-10-01", source: "Вручную и загрузка базы", count: 80 },
  ],
  sources: [
    { name: "Сайт", is_paid: false, is_manual: false, total: 3 },
    { name: "Вручную и загрузка базы", is_paid: false, is_manual: true, total: 80 },
  ],
};

vi.mock("@/lib/hooks/use-company", () => ({
  useCompanyInflow: () => ({ data, isLoading: false, isError: false }),
}));

import { InflowCard } from "./InflowCard";

function todayStat() {
  const label = screen.getByText("Сегодня");
  return within(label.parentElement as HTMLElement);
}

describe("InflowCard", () => {
  it("leaves the base-load bucket out of the numbers until it is switched on", async () => {
    render(<InflowCard />);

    const manual = screen.getByRole("button", { name: /Вручную и загрузка базы/ });
    expect(manual).toHaveAttribute("aria-pressed", "false");
    expect(todayStat().getByText("2")).toBeInTheDocument();
    expect(todayStat().getByText("вчера 1")).toBeInTheDocument();

    await userEvent.click(manual);
    expect(manual).toHaveAttribute("aria-pressed", "true");
    expect(todayStat().getByText("82")).toBeInTheDocument();
  });

  it("switches the table to months", async () => {
    render(<InflowCard />);
    await userEvent.click(screen.getByRole("tab", { name: "По месяцам" }));
    expect(screen.getByRole("columnheader", { name: "Этот месяц" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Прошлый" })).toBeInTheDocument();
  });
});
