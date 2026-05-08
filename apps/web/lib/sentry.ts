/**
 * Browser-side Sentry init guard.
 *
 * `NEXT_PUBLIC_SENTRY_DSN` is inlined at build time (see apps/web/Dockerfile);
 * `initSentry()` checks it at runtime and either:
 *   - silently no-ops (DSN unset — current production state)
 *   - warns once (DSN set but @sentry/nextjs not installed yet)
 *   - calls Sentry.init when both DSN and the package are present
 *
 * The lazy require keeps `@sentry/nextjs` out of the import graph until
 * it's actually configured. When the operator decides to wire Sentry,
 * `pnpm add @sentry/nextjs` flips this from warn-once to live.
 */
let _initialised = false;

export function initSentry(): void {
  if (_initialised) return;
  _initialised = true;

  if (typeof window === "undefined") return;

  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return; // Production default: telemetry off.

  // The package isn't pinned in package.json yet — when the operator
  // installs it, this lazy require will succeed and Sentry init will run.
  // Until then, log a one-shot warning so the empty DSN env var doesn't
  // silently confuse a future debug session.
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Sentry = require("@sentry/nextjs");
    Sentry.init({
      dsn,
      tracesSampleRate: 0.1,
      // Keep the production bundle small — feature flags can be flipped
      // here when we actually start using performance / replay / profiling.
    });
  } catch {
    // eslint-disable-next-line no-console
    console.warn(
      "[sentry] NEXT_PUBLIC_SENTRY_DSN is set but @sentry/nextjs is not installed. " +
        "Run `pnpm add @sentry/nextjs` to enable error reporting.",
    );
  }
}
