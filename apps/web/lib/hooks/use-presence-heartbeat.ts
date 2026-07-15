"use client";

import { useEffect, useRef } from "react";
import { api } from "@/lib/api-client";

const PING_INTERVAL_MS = 60_000;
// A ping only fires if there was genuine interaction within this window —
// an open-but-untouched tab stops counting after one idle minute.
const IDLE_WINDOW_MS = 60_000;
const MOVE_THROTTLE_MS = 5_000;

/**
 * Records ACTIVE working minutes, not «tab is open» time. While the tab is
 * visible AND the user has interacted (pointer / keyboard / scroll / touch)
 * within the last minute, it pings the backend once a minute; the server
 * stamps the current minute (deduped by primary key). Idle time never counts.
 *
 * Mounted once in the authenticated app shell, so it spans the whole session
 * regardless of route changes.
 */
export function usePresenceHeartbeat(enabled: boolean = true) {
  const lastInteraction = useRef<number>(Date.now());

  useEffect(() => {
    if (!enabled) return;

    const bump = () => {
      lastInteraction.current = Date.now();
    };
    // mousemove fires constantly — throttle it so we don't rewrite the ref
    // on every pixel.
    let lastMove = 0;
    const onMove = () => {
      const now = Date.now();
      if (now - lastMove > MOVE_THROTTLE_MS) {
        lastMove = now;
        lastInteraction.current = now;
      }
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") bump();
    };

    window.addEventListener("pointerdown", bump, { passive: true });
    window.addEventListener("keydown", bump);
    window.addEventListener("scroll", bump, { passive: true });
    window.addEventListener("touchstart", bump, { passive: true });
    window.addEventListener("mousemove", onMove, { passive: true });
    document.addEventListener("visibilitychange", onVisible);

    let stopped = false;
    const ping = () => {
      if (stopped) return;
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastInteraction.current > IDLE_WINDOW_MS) return;
      // Fire-and-forget: a dropped ping just loses one minute, never surfaces.
      api.post("/presence/ping").catch(() => {});
    };

    ping(); // count the landing minute if the user arrived active
    const id = window.setInterval(ping, PING_INTERVAL_MS);

    return () => {
      stopped = true;
      window.clearInterval(id);
      window.removeEventListener("pointerdown", bump);
      window.removeEventListener("keydown", bump);
      window.removeEventListener("scroll", bump);
      window.removeEventListener("touchstart", bump);
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled]);
}
