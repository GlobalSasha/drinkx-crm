import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
const { meMock, leadMock } = vi.hoisted(() => ({ meMock: vi.fn(), leadMock: vi.fn() }));
vi.mock("@/lib/hooks/use-me", () => ({ useMe: () => meMock() }));
vi.mock("@/lib/hooks/use-lead", () => ({ useLead: () => leadMock(), useUpdateLead: vi.fn() }));
vi.mock("./PoolLeadPreview", () => ({ PoolLeadPreview: () => <div>Свободная карточка</div> }));
// These hooks belong to the editable card. Preview must never invoke them.
vi.mock("@/lib/hooks/use-pipelines", () => ({ usePipelines: () => { throw new Error("Editable card mounted"); }, DEFAULT_STAGES: [] }));
import { LeadCard } from "./LeadCard";

describe("LeadCard — граница свободной карточки", () => {
  afterEach(() => { meMock.mockReset(); leadMock.mockReset(); });
  it("разрешённый менеджер видит только preview без дочерних запросов", () => {
    meMock.mockReturnValue({ data: { id: "m1", role: "manager", can_access_lead_pool: true } });
    leadMock.mockReturnValue({ data: { assigned_to: null } });
    render(<LeadCard leadId="l1" />);
    expect(screen.getByText("Свободная карточка")).toBeInTheDocument();
  });
  it.each([
    [{ id: "m1", role: "manager", can_access_lead_pool: false }, null],
    [{ id: "m1", role: "manager", can_access_lead_pool: true }, "m2"],
  ])("отказ без разрешения или для чужого лида", (me, assigned) => {
    meMock.mockReturnValue({ data: me });
    leadMock.mockReturnValue({ data: { assigned_to: assigned } });
    render(<LeadCard leadId="l1" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Нет доступа");
    expect(screen.queryByText("Свободная карточка")).toBeNull();
  });
  it.each([
    [{ id: "m1", role: "manager", can_access_lead_pool: false }, "m1"],
    [{ id: "a1", role: "admin" }, null],
    [{ id: "h1", role: "head" }, null],
  ])("свой лид и руководство переходят к полной карточке", (me, assigned) => {
    meMock.mockReturnValue({ data: me });
    leadMock.mockReturnValue({ data: { assigned_to: assigned } });
    // Sentinels prove selection of the existing editable branch.
    expect(() => render(<LeadCard leadId="l1" />)).toThrow("Editable card mounted");
  });
  it("ошибка /me не оставляет вечную загрузку", () => {
    meMock.mockReturnValue({ isError: true });
    leadMock.mockReturnValue({ data: { assigned_to: null } });
    render(<LeadCard leadId="l1" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Не удалось проверить доступ");
  });
});
