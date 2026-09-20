import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

const { claimMock, meMock } = vi.hoisted(() => ({
  claimMock: vi.fn(),
  meMock: vi.fn(),
}));

vi.mock("@/lib/hooks/use-leads", () => ({
  POOL_PAGE_SIZE: 50,
  usePoolLeads: () => ({
    data: {
      items: mockLeads,
      total: mockLeads.length,
      page: 1,
      page_size: 50,
    },
    isLoading: false,
    isError: false,
    isFetching: false,
  }),
  // Значения фильтров и их размеры приходят с сервера (аудит G6).
  usePoolFacets: () => ({
    data: {
      cities: [{ value: "Москва", count: 1 }],
      segments: [{ value: "Ритейл", count: 1 }],
      priorities: [{ value: "A", count: 1 }],
      tiers: [{ value: "A", count: 1 }],
      deal_types: [],
      sources: [{ value: "Выставка", count: 1 }],
      tags: [{ value: "сеть", count: 1 }],
      total: 1,
    },
    isLoading: false,
  }),
  useClaimLead: () => ({ mutate: claimMock }),
}));

vi.mock("@/lib/hooks/use-forms", () => ({
  useForms: () => ({ data: { items: [] } }),
}));

vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => meMock(),
}));

vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({ data: { items: [], total: 0 } }),
}));

import LeadsPoolPage from "./page";
import type { LeadOut } from "@/lib/types";

const mockLeads = [
  {
    id: "lead-1",
    workspace_id: "workspace-1",
    pipeline_id: null,
    stage_id: null,
    company_name: "Альфа Ритейл",
    segment: "Ритейл",
    city: "Москва",
    email: "sales@alpha.example",
    phone: "+7 495 111-22-33",
    website: "https://alpha.example",
    inn: "7701000001",
    source: "Выставка",
    source_id: null,
    tags_json: ["сеть"],
    deal_type: null,
    priority: "A",
    score: 86,
    fit_score: 91,
    blocker: null,
    next_step: null,
    next_action_at: null,
    assignment_status: "pool",
    assigned_to: null,
    assigned_at: null,
    transferred_from: null,
    transferred_at: null,
    is_rotting_stage: false,
    is_rotting_next_step: false,
    last_activity_at: null,
    archived_at: null,
    won_at: null,
    lost_at: null,
    lost_reason: null,
    primary_contact_id: null,
    primary_contact_name: null,
    source_form_id: null,
    source_form_name: null,
    latest_utm: null,
    open_followups_count: 0,
    open_tasks_count: 0,
    commercial_model: null,
    deal_amount: null,
    deal_quantity: null,
    deal_equipment: null,
    priority_label: "Высокий",
    needs_review: false,
    current_stage_days: null,
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-01T09:00:00Z",
  },
  {
    id: "lead-2",
    workspace_id: "workspace-1",
    pipeline_id: null,
    stage_id: null,
    company_name: "Бета Кофе",
    segment: "Кофейни и кафе",
    city: "Санкт-Петербург",
    email: "hello@beta.example",
    phone: "+7 812 444-55-66",
    website: "https://beta.example",
    inn: "7802000002",
    source: "Лендинг",
    source_id: null,
    tags_json: ["horeca"],
    deal_type: null,
    priority: "B",
    score: 68,
    fit_score: 74,
    blocker: null,
    next_step: null,
    next_action_at: null,
    assignment_status: "pool",
    assigned_to: null,
    assigned_at: null,
    transferred_from: null,
    transferred_at: null,
    is_rotting_stage: false,
    is_rotting_next_step: false,
    last_activity_at: null,
    archived_at: null,
    won_at: null,
    lost_at: null,
    lost_reason: null,
    primary_contact_id: null,
    primary_contact_name: null,
    source_form_id: "form-1",
    source_form_name: "Заявка на демо",
    latest_utm: { utm_source: "yandex" },
    open_followups_count: 0,
    open_tasks_count: 0,
    commercial_model: null,
    deal_amount: null,
    deal_quantity: null,
    deal_equipment: null,
    priority_label: "Средний",
    needs_review: false,
    current_stage_days: null,
    created_at: "2026-09-02T10:00:00Z",
    updated_at: "2026-09-02T10:00:00Z",
  },
] satisfies LeadOut[];

function renderPage() {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <LeadsPoolPage />
    </QueryClientProvider>,
  );
}

describe("LeadsPoolPage — доступ к выдаче лидов", () => {
  afterEach(() => {
    claimMock.mockReset();
    meMock.mockReset();
  });

  it("manager не видит элементы выбора и выдачи", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "manager" } });
    renderPage();

    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /Выдать по фильтру/ })).toBeNull();
    expect(screen.queryByRole("region", { name: "Выделенные карточки" })).toBeNull();
  });

  it("head видит чекбоксы и выдачу по фильтру", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    renderPage();

    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(mockLeads.length + 1);
    expect(screen.getByRole("button", { name: /Выдать по фильтру/ })).toBeInTheDocument();
  });

  it("head может выбрать строку и открыть панель выделения", async () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "head" } });
    renderPage();

    await userEvent.click(screen.getByLabelText(`Выбрать ${mockLeads[0].company_name}`));

    const selection = screen.getByRole("region", { name: "Выделенные карточки" });
    expect(within(selection).getByText("Выбрано: 1")).toBeInTheDocument();
    expect(within(selection).getByRole("button", { name: "Выдать менеджеру" })).toBeInTheDocument();
  });

  it("admin видит чекбоксы выбора", () => {
    meMock.mockReturnValue({ data: { id: "me-1", role: "admin" } });
    renderPage();

    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(mockLeads.length + 1);
  });
});
