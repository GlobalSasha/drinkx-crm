import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CompanyVoice } from "@/lib/types";

const { voiceMock } = vi.hoisted(() => ({ voiceMock: vi.fn() }));
vi.mock("@/lib/hooks/use-company", () => ({ useCompanyVoice: (p: string) => voiceMock(p) }));

import { VoiceCard, leadsWord } from "./VoiceCard";

const data = {
  period: "week",
  days: 7,
  groups: [
    {
      group: "objection",
      label: "Возражения",
      items: [
        {
          key: "price",
          label: "Цена, дорого",
          leads: 3,
          previous: 1,
          quotes: [
            { lead_id: "l1", company_name: "Кофейня у дома", author: "Дмитрий", quote: "цена кусается", at: "2026-11-18T10:00:00Z" },
          ],
        },
        { key: "leasing", label: "Нужен лизинг или рассрочка", leads: 1, previous: 1, quotes: [] },
      ],
    },
    {
      group: "competitor",
      label: "Конкуренты",
      items: [{ key: "competitor:Scanomat", label: "Scanomat", leads: 1, previous: 0, quotes: [] }],
    },
  ],
  lost_reasons: [{ reason: "Не устроила цена", count: 2 }],
  comments_total: 40,
  comments_pending: 5,
  last_scan_at: "2026-11-19T00:00:00Z",
} satisfies CompanyVoice;

beforeEach(() => {
  voiceMock.mockReset();
  voiceMock.mockReturnValue({ data, isLoading: false, isError: false });
});

describe("leadsWord", () => {
  it("склоняет", () => {
    expect(leadsWord(1)).toBe("лид");
    expect(leadsWord(3)).toBe("лида");
    expect(leadsWord(5)).toBe("лидов");
    expect(leadsWord(11)).toBe("лидов");
    expect(leadsWord(21)).toBe("лид");
  });
});

describe("VoiceCard", () => {
  it("группы, число лидов, рост к прошлому периоду и причины отказов", () => {
    render(<VoiceCard />);
    expect(screen.getByText("Возражения")).toBeInTheDocument();
    expect(screen.getByText("Цена, дорого")).toBeInTheDocument();
    expect(screen.getByText("3 лида")).toBeInTheDocument();
    expect(screen.getByTitle("в прошлом периоде: 1")).toHaveTextContent("2");
    expect(screen.getByText("Scanomat")).toBeInTheDocument();
    expect(screen.getByText("Не устроила цена")).toBeInTheDocument();
    expect(screen.queryByText(/ждут разметки/)).not.toBeInTheDocument();
  });

  it("по клику раскрывает цитаты со ссылкой на лид", () => {
    render(<VoiceCard />);
    expect(screen.queryByText("«цена кусается»")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Цена, дорого/ }));
    expect(screen.getByText("«цена кусается»")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Кофейня у дома · Дмитрий/ })).toHaveAttribute("href", "/leads/l1");
  });

  it("переключает период", () => {
    render(<VoiceCard />);
    fireEvent.click(screen.getByRole("tab", { name: "Месяц" }));
    expect(voiceMock).toHaveBeenLastCalledWith("month");
  });

  it("пусто: говорит, что ждёт разметки", () => {
    voiceMock.mockReturnValue({
      data: { ...data, groups: [], lost_reasons: [], comments_pending: 12 },
      isLoading: false,
      isError: false,
    });
    render(<VoiceCard />);
    expect(screen.getByText(/12 ждут ночной разметки/)).toBeInTheDocument();
  });
});
