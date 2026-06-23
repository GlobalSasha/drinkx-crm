"use client";
import { useEffect } from "react";

// Intercepts in-app link navigations away from the current page while
// `enabled` is true. The dominant way a manager leaves a lead card is by
// clicking a link elsewhere (the sidebar, a breadcrumb); we catch that click
// in the capture phase, block it, and hand the intended href to `onIntercept`,
// which decides whether to proceed.
//
// Scope (v1): internal `<a href="/…">` clicks to a DIFFERENT page only.
// NOT intercepted: browser back/forward (App Router has no reliable hook and
// history manipulation breaks the back button), modified clicks (new tab),
// programmatic router.push (e.g. «Вернуть в пул» — a deliberate exit).
//
// `onIntercept` must be stable (wrap in useCallback) or the listener
// re-subscribes every render.
export function useLeaveGuard(
  enabled: boolean,
  currentPath: string,
  onIntercept: (href: string) => void,
) {
  useEffect(() => {
    if (!enabled) return;

    function onClick(e: MouseEvent) {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const anchor = target?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!anchor) return;
      if (anchor.target === "_blank" || anchor.hasAttribute("download")) return;

      const href = anchor.getAttribute("href") || "";
      // Internal absolute paths only — skip external, protocol (tel:/mailto:)
      // and hash links.
      if (!href.startsWith("/") || href.startsWith("//")) return;

      const url = new URL(href, window.location.origin);
      if (url.pathname === currentPath) return; // same page (e.g. ?tab= switch)

      e.preventDefault();
      e.stopPropagation();
      onIntercept(href);
    }

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [enabled, currentPath, onIntercept]);
}
