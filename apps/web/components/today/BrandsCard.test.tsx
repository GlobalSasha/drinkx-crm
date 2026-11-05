import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const query = vi.hoisted(() => ({
  current: { data: undefined, isLoading: false, isError: false } as {
    data?: { aeromilk: number; drinkx: number; no_brand: number };
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("@/lib/hooks/use-company", () => ({
  useCompanyBrands: () => query.current,
}));

import { BrandsCard } from "./BrandsCard";

function stat(label: string) {
  return within(screen.getByText(label).parentElement as HTMLElement);
}

describe("BrandsCard", () => {
  beforeEach(() => {
    query.current = { data: undefined, isLoading: false, isError: false };
  });

  it("puts each number under its own brand", () => {
    query.current = { data: { aeromilk: 12, drinkx: 7, no_brand: 0 }, isLoading: false, isError: false };
    render(<BrandsCard />);

    expect(stat("AeroMilk").getByText("12")).toBeInTheDocument();
    expect(stat("DrinkX").getByText("7")).toBeInTheDocument();
    expect(stat("Без бренда").getByText("0")).toBeInTheDocument();
  });

  it("says so when the numbers failed to load", () => {
    query.current = { data: undefined, isLoading: false, isError: true };
    render(<BrandsCard />);

    expect(screen.getByText(/Не удалось загрузить/)).toBeInTheDocument();
    expect(screen.queryByText("AeroMilk")).not.toBeInTheDocument();
  });
});
