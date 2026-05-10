"use client";

/**
 * Error boundary for the authenticated `(app)` route group. Catches
 * render errors on /today, /pipeline, /leads/[id], /automations,
 * /audit, /settings, /forms, /inbox, /leads-pool — anything wrapped
 * by AppShell. Per-route error.tsx files can override this for
 * page-specific recovery affordances.
 *
 * Sprint 2.7 G1: routes the error to Sentry with a route tag so
 * operators can filter "show me all errors on /pipeline today".
 */

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { captureClientException } from "@/lib/sentry-capture";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const pathname = usePathname();

  useEffect(() => {
    captureClientException(error, {
      route: pathname || "(app)",
      tags: { boundary: "(app)/error", digest: error.digest ?? "" },
    });
  }, [error, pathname]);

  return (
    <div className="mx-auto flex max-w-xl flex-col items-start gap-3 p-8">
      <h1 className="text-xl font-semibold">Что-то пошло не так</h1>
      <p className="text-sm text-neutral-600">
        Эту ошибку уже отправили команде. Можно попробовать снова или
        перейти в другой раздел.
      </p>
      {error.digest ? (
        <p className="font-mono text-xs text-neutral-400">ID: {error.digest}</p>
      ) : null}
      <button
        onClick={reset}
        className="mt-2 rounded-md bg-neutral-900 px-3 py-1.5 text-sm text-white hover:bg-neutral-700"
      >
        Попробовать снова
      </button>
    </div>
  );
}
