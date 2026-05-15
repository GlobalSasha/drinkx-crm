"use client";

/**
 * Top-level error boundary — fires when even the root layout fails
 * to render. Has to include its own <html> + <body> because the
 * normal layout chain is broken.
 *
 * Sprint 2.7 G1: reports to Sentry alongside the existing fallback UI.
 */

import { useEffect } from "react";

import { T } from "@/lib/design-system";
import { captureClientException } from "@/lib/sentry-capture";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    captureClientException(error, {
      route: "__global__",
      tags: { boundary: "global-error", digest: error.digest ?? "" },
    });
  }, [error]);

  return (
    <html lang="ru">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          padding: "2rem",
          color: "#111",
          background: "#fafafa",
        }}
      >
        <h1 className="type-card-title mb-2">
          Что-то пошло не так
        </h1>
        <p style={{ color: "#666", marginBottom: "1rem" }}>
          Мы уже знаем — попробуйте обновить страницу.
        </p>
        {error.digest ? (
          <p className={`${T.mono} text-[#999]`}>
            ID: {error.digest}
          </p>
        ) : null}
        <button
          onClick={reset}
          style={{
            marginTop: "1rem",
            padding: "0.5rem 1rem",
            background: "#111",
            color: "#fff",
            border: 0,
            borderRadius: "0.25rem",
            cursor: "pointer",
          }}
        >
          Перезагрузить
        </button>
      </body>
    </html>
  );
}
