import { describe, expect, it } from "vitest";
import { safeHref } from "./safe-url";

describe("safeHref", () => {
  it("passes through http and https URLs", () => {
    expect(safeHref("https://example.com/x")).toBe("https://example.com/x");
    expect(safeHref("http://example.com")).toBe("http://example.com");
  });

  it("trims surrounding whitespace on safe URLs", () => {
    expect(safeHref("  https://example.com  ")).toBe("https://example.com");
  });

  it("rejects javascript: and other dangerous schemes", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("data:text/html,<script>")).toBeUndefined();
    expect(safeHref("mailto:a@b.com")).toBeUndefined();
  });

  it("rejects relative / malformed URLs", () => {
    expect(safeHref("/relative/path")).toBeUndefined();
    expect(safeHref("not a url")).toBeUndefined();
  });

  it("returns undefined for empty / nullish input", () => {
    expect(safeHref("")).toBeUndefined();
    expect(safeHref(null)).toBeUndefined();
    expect(safeHref(undefined)).toBeUndefined();
  });
});
