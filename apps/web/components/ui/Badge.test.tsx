import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders its children as visible text", () => {
    render(<Badge>Closed won</Badge>);
    expect(screen.getByText("Closed won")).toBeInTheDocument();
  });

  it("applies the variant class for non-default variants", () => {
    render(<Badge variant="rose">Lost</Badge>);
    expect(screen.getByText("Lost")).toHaveClass("text-rose");
  });

  it("merges a custom className", () => {
    render(<Badge className="custom-x">Tag</Badge>);
    expect(screen.getByText("Tag")).toHaveClass("custom-x");
  });
});
