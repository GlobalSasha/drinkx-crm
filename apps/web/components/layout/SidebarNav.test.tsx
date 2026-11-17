import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SidebarNav } from "./SidebarNav";

describe("SidebarNav", () => {
  it("пункт с newTab — обычная ссылка в новую вкладку, без клиентского перехода", () => {
    render(
      <SidebarNav
        activeId={null}
        items={[{ id: "kp", label: "КП", href: "/kp", icon: null, newTab: true }]}
      />,
    );
    const link = screen.getByRole("link", { name: "КП" });
    expect(link.getAttribute("href")).toBe("/kp");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener");
  });
});
