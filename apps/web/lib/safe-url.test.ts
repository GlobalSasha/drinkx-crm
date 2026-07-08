import { describe, expect, it } from "vitest";
import { safeHref, socialHref } from "./safe-url";

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

describe("socialHref", () => {
  it("builds a link from a bare handle", () => {
    expect(socialHref("@anthonykolchin", "telegram")).toBe("https://t.me/anthonykolchin");
    expect(socialHref("anthonykolchin", "telegram")).toBe("https://t.me/anthonykolchin");
    expect(socialHref("john.doe", "instagram")).toBe("https://instagram.com/john.doe");
    expect(socialHref("@jane", "linkedin")).toBe("https://linkedin.com/in/jane");
  });

  it("adds https:// to a bare domain", () => {
    expect(socialHref("t.me/x", "telegram")).toBe("https://t.me/x");
    expect(socialHref("linkedin.com/in/x", "linkedin")).toBe("https://linkedin.com/in/x");
    expect(socialHref("www.facebook.com/x", "facebook")).toBe("https://www.facebook.com/x");
  });

  it("passes through an existing safe URL", () => {
    expect(socialHref("https://t.me/x", "telegram")).toBe("https://t.me/x");
    expect(socialHref("  https://t.me/x  ", "telegram")).toBe("https://t.me/x");
  });

  it("rejects dangerous or empty input", () => {
    expect(socialHref("javascript:alert(1)", "telegram")).toBeUndefined();
    expect(socialHref("hello world", "telegram")).toBeUndefined();
    expect(socialHref("@", "telegram")).toBeUndefined();
    expect(socialHref("", "telegram")).toBeUndefined();
    expect(socialHref(null, "telegram")).toBeUndefined();
  });
});
