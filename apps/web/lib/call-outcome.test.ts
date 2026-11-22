import { beforeEach, describe, expect, it } from "vitest";
import { MAX_CALL_MS, markPendingCall, takePendingCall } from "./call-outcome";

describe("pending call", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("asks once after a real call to the same lead", () => {
    markPendingCall("L1", 1_000);
    expect(takePendingCall("L1", 31_000)).toBe(true);
    expect(takePendingCall("L1", 32_000)).toBe(false);
  });

  it("does not ask when the manager came straight back", () => {
    markPendingCall("L1", 1_000);
    expect(takePendingCall("L1", 3_000)).toBe(false);
    // ...but still asks later once the call is long enough
    expect(takePendingCall("L1", 20_000)).toBe(true);
  });

  it("does not ask on another lead's card", () => {
    markPendingCall("L1", 0);
    expect(takePendingCall("L2", 60_000)).toBe(false);
    expect(takePendingCall("L1", 60_000)).toBe(true);
  });

  it("drops a stale call without asking", () => {
    markPendingCall("L1", 0);
    expect(takePendingCall("L1", MAX_CALL_MS + 1)).toBe(false);
    expect(takePendingCall("L1", MAX_CALL_MS + 2)).toBe(false);
  });
});
