/**
 * Browser-side capture helper. Mirrors `app/common/sentry_capture.py`
 * on the API side: a single chokepoint that error boundaries call
 * when something throws, with a uniform `tags` shape so issues group
 * sensibly in Sentry.
 *
 * No-op when `@sentry/nextjs` is not yet installed. The `initSentry()`
 * guard in `lib/sentry.ts` flips on once the operator runs
 * `pnpm add @sentry/nextjs` and sets `NEXT_PUBLIC_SENTRY_DSN`.
 */

type Tags = Record<string, string>;
type Extra = Record<string, unknown>;

export function captureClientException(
  error: unknown,
  options: { route?: string; tags?: Tags; extra?: Extra } = {},
): void {
  if (typeof window === "undefined") return;

  try {
    // Lazy require so this module doesn't pull `@sentry/nextjs` into
    // the import graph until it's actually installed.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Sentry = require("@sentry/nextjs");
    Sentry.withScope((scope: { setTag: (k: string, v: string) => void; setExtras: (e: Extra) => void; setFingerprint: (fp: string[]) => void }) => {
      if (options.route) {
        scope.setTag("route", options.route);
        scope.setFingerprint(["render-error", options.route]);
      }
      if (options.tags) {
        for (const [k, v] of Object.entries(options.tags)) {
          scope.setTag(k, v);
        }
      }
      if (options.extra) {
        scope.setExtras(options.extra);
      }
      Sentry.captureException(error);
    });
  } catch {
    // Sentry not installed yet — log to console and move on. Once
    // `pnpm add @sentry/nextjs` is run + `NEXT_PUBLIC_SENTRY_DSN` is
    // set, this branch is replaced by the real capture above.
    // eslint-disable-next-line no-console
    console.error("[sentry-capture]", error, options);
  }
}
