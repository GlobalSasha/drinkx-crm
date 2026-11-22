import { describe, expect, it } from "vitest";
import { detectPushSupport, urlBase64ToUint8Array, type PushEnv } from "./push";

const base: PushEnv = {
  hasServiceWorker: true,
  hasPushManager: true,
  hasNotification: true,
  userAgent: "Mozilla/5.0 (Linux; Android 14) Chrome/130",
  maxTouchPoints: 5,
  standalone: false,
};

const SAFARI_TAB = {
  ...base,
  hasPushManager: false,
  hasNotification: false,
  userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1",
};

describe("detectPushSupport", () => {
  it("Android / desktop browser with push APIs", () => {
    expect(detectPushSupport(base)).toBe("supported");
  });
  it("iPhone in a Safari tab → must add to home screen first", () => {
    expect(detectPushSupport(SAFARI_TAB)).toBe("ios-needs-install");
  });
  it("iPad reporting itself as a Mac with touch", () => {
    expect(
      detectPushSupport({ ...SAFARI_TAB, userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" }),
    ).toBe("ios-needs-install");
  });
  it("iPhone home-screen app exposes push → supported", () => {
    expect(detectPushSupport({ ...base, userAgent: SAFARI_TAB.userAgent, standalone: true })).toBe("supported");
  });
  it("old iPhone app without push APIs → unsupported, not an install hint", () => {
    expect(detectPushSupport({ ...SAFARI_TAB, standalone: true })).toBe("unsupported");
  });
});

describe("urlBase64ToUint8Array", () => {
  it("decodes URL-safe base64 without padding", () => {
    expect(Array.from(urlBase64ToUint8Array("AP-_"))).toEqual([0x00, 0xff, 0xbf]);
  });
});
