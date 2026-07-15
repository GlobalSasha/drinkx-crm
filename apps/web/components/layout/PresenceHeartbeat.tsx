"use client";

import { usePresenceHeartbeat } from "@/lib/hooks/use-presence-heartbeat";

/**
 * Mount-only client component: runs the active-time heartbeat for the whole
 * authenticated session. Renders nothing.
 */
export function PresenceHeartbeat() {
  usePresenceHeartbeat(true);
  return null;
}
