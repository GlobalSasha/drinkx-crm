import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CompanyManagerSpeed, SpeedStats } from "@/lib/types";

const { speedMock } = vi.hoisted(() => ({ speedMock: vi.fn() }));
vi.mock("@/lib/hooks/use-company", () => ({ useCompanyManagerSpeed: () => speedMock() }));

import { ManagerSpeedCard, speedTone } from "./ManagerSpeedCard";

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
        forms: { total: 17, handled: 10, hanging: 7, median_hours: 17, median_work_hours: 5 },
        own: { total: 2, handled: 1, hanging: 1, median_hours: 0.9, median_work_hours: 0.9 },
      },
      days: [
        { day: "2026-11-09", forms: 3, own: null },
        { day: "2026-11-10", forms: null, own: null },
        { day: "2026-11-11", forms: 8, own: 0.9 },
      ],
      hanging: [
        { lead_id: "l1", company_name: "Кофейня у дома", kind: "form", hours: 30 },
        { lead_id: "l2", company_name: "Свой без звонка", kind: "own", hours: 5 },
      ],
    },
  ],
} satisfies CompanyManagerSpeed;

beforeEach(() => speedMock.mockReturnValue({ data, isLoading: false, isError: false }));

describe("speedTone", () => {
  it("красит по порогам рабочих часов", () => {
    expect(speedTone(0.5)).toBe("success");
    expect(speedTone(1)).toBe("success");
    expect(speedTone(3)).toBe("warning");
    expect(speedTone(5)).toBe("rose");
  });
});

describe("ManagerSpeedCard", () => {
  it("за неделю: скорость с цветом, календарь мелко, доли и плашка «висят»", () => {
    render(<ManagerSpeedCard />);
    expect(screen.getByText("Дмитрий")).toBeInTheDocument();
    expect(screen.getByText("5 ч")).toHaveClass("text-rose");
    expect(screen.getByText("17 ч по календарю")).toBeInTheDocument();
    expect(screen.getByText("10 из 17 обработано")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "обработано 10 из 17, висят 7" })).toBeInTheDocument();
    expect(screen.getAllByLabelText("по дням недели")).toHaveLength(2);
  });

  it("плашка «висят» раскрывает лиды своего вида", () => {
    render(<ManagerSpeedCard />);
    fireEvent.click(screen.getByRole("button", { name: /7 висят/ }));
    expect(screen.getByRole("link", { name: /Кофейня у дома/ })).toHaveAttribute("href", "/leads/l1");
    expect(screen.queryByText("Свой без звонка")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /1 висит/ }));
    expect(screen.getByText("Свой без звонка")).toBeInTheDocument();
    expect(screen.queryByText("Кофейня у дома")).not.toBeInTheDocument();
  });

  it("сегодня: без скорости — понятная подпись, без графика и раскрытия", () => {
    render(<ManagerSpeedCard />);
    fireEvent.click(screen.getByRole("tab", { name: "Сегодня" }));
    expect(screen.getByText("ещё никого не обработал")).toBeInTheDocument();
    expect(screen.getByText("нет новых")).toBeInTheDocument();
    expect(screen.queryByLabelText("по дням недели")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /висят/ })).not.toBeInTheDocument();
  });

  it("подсказка «как считается» открывается по кнопке", () => {
    render(<ManagerSpeedCard />);
    expect(screen.queryByText(/запись первого разговора не в счёт/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Как считается" }));
    expect(screen.getByText(/запись первого разговора не в счёт/)).toBeInTheDocument();
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
