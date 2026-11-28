import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const query = vi.hoisted(() => ({
  current: { data: undefined, isLoading: false, isError: false } as {
    data?: unknown;
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("@/lib/hooks/use-company", () => ({
  useCompanyDigest: () => query.current,
}));

import { DigestCard, periodLabel } from "./DigestCard";

const newLeads = Array.from({ length: 10 }, (_, i) => ({
  id: `n${i}`,
  company_name: `Новый ${i + 1}`,
  city: i === 0 ? "Казань" : null,
  source: i === 0 ? "Сайт" : null,
  manager: i === 0 ? "Дмитрий" : null,
  created_at: "2026-11-27T10:00:00Z",
}));

const digest = {
  created_at: "2026-11-28T00:05:00Z",
  period_from: "2026-11-23T00:00:00Z",
  period_to: "2026-11-28T00:00:00Z",
  comments: 57,
  leads: 34,
  sections: [
    {
      key: "progress",
      title: "Продвинулись",
      items: [{ text: "Гуру кофе: рассрочка на 3 месяца", leads: [{ id: "l1", company_name: "Гуру кофе" }] }],
    },
  ],
};

describe("DigestCard", () => {
  beforeEach(() => {
    query.current = {
      data: { digest, stale: false, new_leads_from: "2026-11-23T00:00:00Z", new_leads: newLeads },
      isLoading: false,
      isError: false,
    };
  });

  it("shows the period, the lines with links to leads, and no warning when fresh", () => {
    render(<DigestCard />);
    expect(screen.getByText(/57 комментариев по 34 лидам/)).toBeInTheDocument();
    expect(screen.getByText("Продвинулись")).toBeInTheDocument();
    expect(screen.getByText(/рассрочка на 3 месяца/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Гуру кофе →" })).toHaveAttribute("href", "/leads/l1");
    expect(screen.queryByText(/не обновлялась/)).not.toBeInTheDocument();
  });

  it("lists new leads, eight first, and expands to all", () => {
    render(<DigestCard />);
    expect(screen.getByText("Новые лиды · 10")).toBeInTheDocument();
    expect(screen.getByText("Казань · Сайт · Дмитрий")).toBeInTheDocument();
    expect(screen.queryByText("Новый 9")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Все новые лиды (10)" }));
    expect(screen.getByText("Новый 10")).toBeInTheDocument();
  });

  it("warns when the nightly run did not come through", () => {
    query.current = {
      data: { digest, stale: true, new_leads_from: "2026-11-23T00:00:00Z", new_leads: [] },
      isLoading: false,
      isError: false,
    };
    render(<DigestCard />);
    expect(screen.getByText(/ночной разбор не прошёл/)).toBeInTheDocument();
    expect(screen.getByText("За 5 дней новых лидов не было.")).toBeInTheDocument();
  });

  it("explains an empty start", () => {
    query.current = {
      data: { digest: null, stale: true, new_leads_from: "2026-11-23T00:00:00Z", new_leads: [] },
      isLoading: false,
      isError: false,
    };
    render(<DigestCard />);
    expect(screen.getByText(/Сводки ещё нет/)).toBeInTheDocument();
  });

  it("formats the period within one month and across two", () => {
    expect(periodLabel("2026-11-23T12:00:00Z", "2026-11-28T12:00:00Z")).toBe("23–28 ноября");
    expect(periodLabel("2026-11-29T12:00:00Z", "2026-12-03T12:00:00Z")).toBe("29 ноября – 3 декабря");
  });
});
