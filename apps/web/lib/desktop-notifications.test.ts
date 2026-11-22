import { describe, expect, it } from "vitest";
import { pickNewForDesktop } from "./desktop-notifications";
import type { NotificationOut } from "./types";

function n(id: string, kind: string, read = false): NotificationOut {
  return {
    id,
    kind,
    title: "t",
    body: "b",
    lead_id: "lead-1",
    read_at: read ? "2026-11-22T10:00:00Z" : null,
    created_at: "2026-11-22T10:00:00Z",
  };
}

describe("pickNewForDesktop", () => {
  it("returns only new unread leads and inbound emails", () => {
    const items = [
      n("1", "lead_inbound"),
      n("2", "email_inbound"),
      n("3", "mention"),
      n("4", "lead_inbound", true),
    ];
    expect(pickNewForDesktop(items, new Set()).map((x) => x.id)).toEqual(["1", "2"]);
  });

  it("skips items already shown, so two polls never pop the same item twice", () => {
    const items = [n("1", "lead_inbound"), n("2", "email_inbound")];
    const seen = new Set(["1"]);
    expect(pickNewForDesktop(items, seen).map((x) => x.id)).toEqual(["2"]);
  });
});
