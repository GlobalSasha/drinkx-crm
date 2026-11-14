import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CompanyManagerSpeed, SpeedStats } from "@/lib/types";

const { speedMock } = vi.hoisted(() => ({ speedMock: vi.fn() }));
vi.mock("@/lib/hooks/use-company", () => ({ useCompanyManagerSpeed: () => speedMock() }));

import { ManagerSpeedCard } from "./ManagerSpeedCard";

const empty: SpeedStats = { total: 0, handled: 0, hanging: 0, median_hours: null, median_work_hours: null };

const data = {
  timezone: "Europe/Moscow",
  today: "2026-11-11",
  week_from: "2026-11-09",
  managers: [
    {
      manager_id: "m1",
      name: "Дмитрий",
      today: {
        forms: { total: 2, handled: 0, hanging: 2, median_hours: null, median_work_hours: null },
        own: empty,
      },
      week: {
        forms: { total: 21, handled: 14, hanging: 7, median_hours: 17, median_work_hours: 3 },
        own: { total: 5, handled: 1, hanging: 4, median_hours: 0.5, median_work_hours: 0 },
      },
      hanging: [{ lead_id: "l1", company_name: "Кофейня у дома", kind: "form", hours: 30 }],
    },
  ],
} satisfies CompanyManagerSpeed;

beforeEach(() => speedMock.mockReturnValue({ data, isLoading: false, isError: false }));

describe("ManagerSpeedCard", () => {
  it("за неделю показывает обе скорости, штуки и висящие лиды", () => {
    render(<ManagerSpeedCard />);
    expect(screen.getByText("Дмитрий")).toBeInTheDocument();
    expect(screen.getByText("раб. 3 ч")).toBeInTheDocument();
    expect(screen.getByText("кален. 17 ч")).toBeInTheDocument();
    expect(screen.getByText("раб. 0 мин")).toBeInTheDocument(); // ночь — не рабочее время
    expect(screen.getByText(/пришло 21 · обработано 14/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Кофейня у дома/ })).toHaveAttribute("href", "/leads/l1");
  });

  it("сегодня — свои цифры, без скорости там, где никто не обработан", () => {
    render(<ManagerSpeedCard />);
    fireEvent.click(screen.getByRole("tab", { name: "Сегодня" }));
    expect(screen.getByText(/пришло 2 · обработано 0/)).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.queryByText("Висят дольше всех")).not.toBeInTheDocument();
  });

  it("пустая неделя и ошибка", () => {
    speedMock.mockReturnValue({ data: { ...data, managers: [] }, isLoading: false, isError: false });
    const { rerender } = render(<ManagerSpeedCard />);
    expect(screen.getByText(/новых заявок с сайта и своих лидов нет/)).toBeInTheDocument();
    speedMock.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    rerender(<ManagerSpeedCard />);
    expect(screen.getByText(/Не удалось загрузить/)).toBeInTheDocument();
  });
});
