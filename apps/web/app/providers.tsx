"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { initSentry } from "@/lib/sentry";
import { captureClientException } from "@/lib/sentry-capture";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, refetchOnWindowFocus: false },
        },
      })
  );
  // Browser-only Sentry init guard — no-ops when DSN unset (current
  // production state). See apps/web/lib/sentry.ts for the lazy-require
  // logic that engages once @sentry/nextjs is pinned.
  useEffect(() => {
    initSentry();

    // Sprint 2.7 G1: surface uncaught errors that fall outside React
    // render boundaries (event handlers, async data fetches, third-
    // party scripts). React error.tsx + global-error.tsx cover
    // render-time crashes; these handle the rest.
    const onError = (event: ErrorEvent) => {
      captureClientException(event.error ?? event.message, {
        tags: { boundary: "window.onerror" },
      });
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      captureClientException(event.reason, {
        tags: { boundary: "unhandledrejection" },
      });
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
