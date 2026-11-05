import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LeadOut } from "@/lib/types";
import { LeadInfoBlock } from "./LeadInfoBlock";

const mutateAsync = vi.fn().mockResolvedValue({});

vi.mock("@/lib/hooks/use-lead-v2", () => ({
  useUpdateDealFields: () => ({ mutateAsync, isPending: false }),
}));
vi.mock("@/lib/hooks/use-lead", () => ({
  useUpdateLead: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/lib/hooks/use-me", () => ({ useMe: () => ({ data: undefined }) }));
vi.mock("@/lib/hooks/use-pipelines", () => ({ usePipelines: () => ({ data: [] }) }));
vi.mock("@/lib/hooks/use-users", () => ({ useUsers: () => ({ data: undefined }) }));
vi.mock("./EnrichmentControl", () => ({ EnrichmentControl: () => null }));
vi.mock("@/components/lead-card/PipelineMoveModal", () => ({ PipelineMoveModal: () => null }));

function lead(overrides: Partial<LeadOut>): LeadOut {
  return { id: "lead-1", deal_equipment: "S400", deal_brand: null, ...overrides } as LeadOut;
}

function openBrandSelect() {
  fireEvent.click(screen.getByText("Бренд"));
  return screen.getByRole("combobox") as HTMLSelectElement;
}

describe("LeadInfoBlock — бренд", () => {
  beforeEach(() => mutateAsync.mockClear());

  it("показывает бренд рядом с моделью, которая не меняется", () => {
    render(<LeadInfoBlock lead={lead({ deal_brand: "DrinkX" })} />);
    expect(screen.getByText("DrinkX")).toBeTruthy();
    expect(screen.getByText("S400")).toBeTruthy();
  });

  it("предлагает ровно два значения и сохраняет выбранное", async () => {
    render(<LeadInfoBlock lead={lead({})} />);
    const select = openBrandSelect();
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(["", "AeroMilk", "DrinkX"]);

    fireEvent.change(select, { target: { value: "AeroMilk" } });
    fireEvent.blur(select);

    await vi.waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ deal_brand: "AeroMilk" }),
    );
  });

  it("очистка отправляет null, а не пустую строку", async () => {
    render(<LeadInfoBlock lead={lead({ deal_brand: "DrinkX" })} />);
    const select = openBrandSelect();
    expect(select.value).toBe("DrinkX");

    fireEvent.change(select, { target: { value: "" } });
    fireEvent.blur(select);

    await vi.waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ deal_brand: null }),
    );
  });
});
