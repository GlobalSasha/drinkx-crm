"use client";

import { useEffect } from "react";

const PREFIX_RE = /^\(\d+\+?\)\s/;

/** «(3) DrinkX CRM» for 3 unread, the bare title for 0. Idempotent:
 *  an existing «(N) » prefix is replaced, never stacked. */
export function withUnreadPrefix(title: string, unread: number): string {
  const base = title.replace(PREFIX_RE, "");
  if (unread <= 0) return base;
  return `(${unread > 99 ? "99+" : unread}) ${base}`;
}

/** Keeps the unread counter in the tab title. Next.js rewrites the
 *  <title> on navigation, so a MutationObserver re-applies the prefix
 *  whenever the title changes underneath us. */
export function useUnreadTitle(unread: number): void {
  useEffect(() => {
    const apply = () => {
      const next = withUnreadPrefix(document.title, unread);
      if (next !== document.title) document.title = next;
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.head, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    return () => {
      observer.disconnect();
      document.title = withUnreadPrefix(document.title, 0);
    };
  }, [unread]);
}
