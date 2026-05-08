"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { initSentry } from "@/lib/sentry";

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
  }, []);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
