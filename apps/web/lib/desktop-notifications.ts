"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import type { NotificationListOut, NotificationOut } from "@/lib/types";

/** Kinds worth a system pop-up: a new lead and a new inbound email. */
export const DESKTOP_KINDS: ReadonlySet<string> = new Set([
  "lead_inbound",
  "email_inbound",
]);

const POLL_MS = 30_000;
const PERMISSION_EVENT = "drinkx:notification-permission";

/** Unread desktop-worthy items not shown yet. Pure — unit-tested. */
export function pickNewForDesktop(
  items: NotificationOut[],
  seen: ReadonlySet<string>,
): NotificationOut[] {
  return items.filter(
    (n) => n.read_at == null && DESKTOP_KINDS.has(n.kind) && !seen.has(n.id),
  );
}

/** System pop-ups work on desktop browsers only. On phones a plain tab
 *  can't show them (iPhone: never; Android: needs a service worker) —
 *  that is phase 3 (PWA + push). */
export function desktopNotificationsSupported(): boolean {
  if (typeof window === "undefined" || !("Notification" in window)) return false;
  return !window.matchMedia?.("(pointer: coarse)").matches;
}

function readPermission(): NotificationPermission | "unsupported" {
  return desktopNotificationsSupported() ? Notification.permission : "unsupported";
}

/** Current permission + a request function for the «Включить» button. */
export function useDesktopPermission() {
  const [permission, setPermission] = useState<
    NotificationPermission | "unsupported"
  >("unsupported");

  useEffect(() => {
    setPermission(readPermission());
    const sync = () => setPermission(readPermission());
    window.addEventListener(PERMISSION_EVENT, sync);
    return () => window.removeEventListener(PERMISSION_EVENT, sync);
  }, []);

  const request = useCallback(async () => {
    if (!desktopNotificationsSupported()) return;
    await Notification.requestPermission();
    window.dispatchEvent(new Event(PERMISSION_EVENT));
  }, []);

  return { permission, request };
}

/** Shows a system pop-up for each NEW lead / inbound email while the tab
 *  is hidden. The first load only remembers what is already there, so
 *  opening the CRM never fires a burst of old items. */
export function useDesktopNotifications(): void {
  const router = useRouter();
  const { permission } = useDesktopPermission();
  const enabled = permission === "granted";
  const seen = useRef<Set<string> | null>(null);

  const { data } = useQuery({
    queryKey: ["notifications", "desktop"],
    queryFn: () =>
      api.get<NotificationListOut>("/notifications?unread=true&page=1&page_size=10"),
    enabled,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
  });

  useEffect(() => {
    if (!enabled || !data) return;
    if (seen.current === null) {
      seen.current = new Set(data.items.map((n) => n.id));
      return;
    }
    const fresh = pickNewForDesktop(data.items, seen.current);
    for (const n of fresh) {
      seen.current.add(n.id);
      if (document.visibilityState !== "hidden") continue;
      try {
        const popup = new Notification(n.title, { body: n.body, tag: n.id });
        popup.onclick = () => {
          window.focus();
          if (n.lead_id) router.push(`/leads/${n.lead_id}`);
          popup.close();
        };
      } catch {
        // Some browsers refuse the constructor (no service worker) —
        // the bell and the tab-title counter still show the item.
      }
    }
  }, [data, enabled, router]);
}
