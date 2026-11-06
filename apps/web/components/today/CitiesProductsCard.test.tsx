import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const query = vi.hoisted(() => ({
  current: { data: undefined, isLoading: false, isError: false } as {
    data?: unknown;
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("@/lib/hooks/use-company", () => ({
  useCompanyCitiesProducts: () => query.current,
}));

import { CitiesProductsCard } from "./CitiesProductsCard";

const cities = Array.from({ length: 12 }, (_, i) => ({ name: `Город ${i + 1}`, count: 20 - i }));

describe("CitiesProductsCard", () => {
  beforeEach(() => {
    query.current = {
      data: {
        total: 100,
        cities,
        no_city: 40,
        products: [{ name: "S400", count: 7 }, { name: "AeroMilk", count: 3 }],
        no_product: 90,
      },
      isLoading: false,
      isError: false,
    };
  });

  it("shows counts for cities and products, including the unknown ones", () => {
    render(<CitiesProductsCard />);
    const row = (name: string) => within(screen.getByText(name).closest("li") as HTMLElement);

    expect(row("Город 1").getByText("20")).toBeInTheDocument();
    expect(row("Город не указан").getByText("40")).toBeInTheDocument();
    expect(row("S400").getByText("7")).toBeInTheDocument();
    expect(row("Продукт не указан").getByText("90")).toBeInTheDocument();
  });

  it("shows the top ten cities and expands to all", () => {
    render(<CitiesProductsCard />);
    expect(screen.queryByText("Город 11")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Все города (12)" }));
    expect(screen.getByText("Город 12")).toBeInTheDocument();
  });

  it("says so when the numbers failed to load", () => {
    query.current = { data: undefined, isLoading: false, isError: true };
    render(<CitiesProductsCard />);
    expect(screen.getByText(/Не удалось загрузить/)).toBeInTheDocument();
  });
});
