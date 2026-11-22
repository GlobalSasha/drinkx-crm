"use client";

import { api } from "@/lib/api-client";

/** Push on this device:
 *  - "supported": the browser can subscribe (Android/desktop, or iPhone
 *    app opened from the home screen);
 *  - "ios-needs-install": iPhone/iPad in a Safari tab — Apple only
 *    delivers push to an app added to the home screen;
 *  - "unsupported": anything else. */
export type PushSupport = "supported" | "ios-needs-install" | "unsupported";

export interface PushEnv {
  hasServiceWorker: boolean;
  hasPushManager: boolean;
  hasNotification: boolean;
  userAgent: string;
  maxTouchPoints: number;
  standalone: boolean;
}

export function readPushEnv(): PushEnv {
  const nav = navigator as Navigator & { standalone?: boolean };
  return {
    hasServiceWorker: "serviceWorker" in navigator,
    hasPushManager: "PushManager" in window,
    hasNotification: "Notification" in window,
    userAgent: navigator.userAgent,
    maxTouchPoints: navigator.maxTouchPoints ?? 0,
    standalone:
      nav.standalone === true || !!window.matchMedia?.("(display-mode: standalone)").matches,
  };
}

/** Pure — unit-tested. */
export function detectPushSupport(env: PushEnv): PushSupport {
  if (env.hasServiceWorker && env.hasPushManager && env.hasNotification) return "supported";
  const isIOS =
    /iPhone|iPad|iPod/.test(env.userAgent) ||
    // iPadOS reports itself as a Mac with touch.
    (/Macintosh/.test(env.userAgent) && env.maxTouchPoints > 1);
  if (isIOS && !env.standalone) return "ios-needs-install";
  return "unsupported";
}

/** VAPID public key (URL-safe base64) → bytes for `applicationServerKey`. */
export function urlBase64ToUint8Array(b64: string): Uint8Array {
  const padded = (b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

/** Set while this device has a server-side push subscription: the
 *  in-tab desktop pop-ups (lib/desktop-notifications.ts) stand down so
 *  nothing pops up twice. Per-device convenience. */
export const PUSH_ON_KEY = "drinkx:push-on";

export function pushFlagOn(): boolean {
  try {
    return window.localStorage.getItem(PUSH_ON_KEY) === "1";
  } catch {
    return false;
  }
}

function setPushFlag(on: boolean): void {
  try {
    if (on) window.localStorage.setItem(PUSH_ON_KEY, "1");
    else window.localStorage.removeItem(PUSH_ON_KEY);
  } catch {
    /* storage unavailable */
  }
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  } catch {
    return null;
  }
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await registerServiceWorker();
  if (!reg || !("pushManager" in reg)) return null;
  return reg.pushManager.getSubscription();
}

export interface PushConfig {
  enabled: boolean;
  public_key: string | null;
}

/** Ask permission, subscribe this device and register it on the server. */
export async function enablePush(config: PushConfig): Promise<"on" | "denied" | "error"> {
  if (!config.enabled || !config.public_key) return "error";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  const reg = await registerServiceWorker();
  if (!reg) return "error";
  try {
    const sub =
      (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(config.public_key) as BufferSource,
      }));
    const json = sub.toJSON();
    await api.post("/notifications/push/subscription", {
      endpoint: json.endpoint,
      keys: json.keys,
    });
    setPushFlag(true);
    return "on";
  } catch {
    return "error";
  }
}

export async function disablePush(): Promise<void> {
  const sub = await currentSubscription();
  if (sub) {
    try {
      await api.post("/notifications/push/unsubscribe", { endpoint: sub.endpoint });
    } finally {
      await sub.unsubscribe();
    }
  }
  setPushFlag(false);
}
