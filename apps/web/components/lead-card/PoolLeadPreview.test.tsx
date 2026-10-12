import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LeadOut } from "@/lib/types";
const { claimMock, state } = vi.hoisted(() => ({ claimMock: vi.fn(), state: { pending: false } }));
vi.mock("@/lib/hooks/use-leads", () => ({ useClaimLead: () => ({ mutate: claimMock, isPending: state.pending }) }));
import { PoolLeadPreview } from "./PoolLeadPreview";
const lead = { id: "l1", company_name: "Компания", city: "Москва", email: "contact@example.com" } as LeadOut;
function mount() {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}><PoolLeadPreview lead={lead} /></QueryClientProvider>);
  return invalidate;
}
describe("PoolLeadPreview", () => {
  afterEach(() => { claimMock.mockReset(); state.pending = false; });
  it("показывает данные и только самостоятельное назначение", async () => {
    mount();
    expect(screen.getByText("contact@example.com")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByRole("textbox")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Взять себе" }));
    expect(claimMock).toHaveBeenCalledWith("l1", expect.any(Object));
  });
  it.each([409, 404])("поясняет гонку назначения (%s)", async (status) => {
    claimMock.mockImplementation((_id, options) => options.onError({ status }));
    const invalidate = mount();
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("alert")).toHaveTextContent("Лид уже взят другим менеджером");
    if (status === 404) expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me"] });
  });
  it("после отзыва обновляет разрешение и показывает отказ", async () => {
    claimMock.mockImplementation((_id, options) => options.onError({ status: 403 }));
    const invalidate = mount();
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("alert")).toHaveTextContent("Доступ к базе отозван");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["lead", "l1"] });
  });
  it("отключает кнопку на время назначения", () => {
    state.pending = true;
    mount();
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
