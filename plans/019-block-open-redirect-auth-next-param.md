# Plan 019: Block open-redirect via the `next` param in the auth flow

> **Executor instructions**: Follow step by step. Run every verification
> command and confirm the expected result before moving on. Honor the STOP
> conditions. When done, update this plan's row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/web/app/auth/callback/route.ts apps/web/app/sign-in/page.tsx`
> If either file changed, compare against the "Current state" excerpts before
> proceeding; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

The auth flow takes a `next` query parameter and redirects to it after a
successful login, with no validation. Because `next` can be an absolute or
protocol-relative URL, a link like `/sign-in?next=https://evil.com` (or an
OAuth/magic-link that carries that `next`) lands the user on an attacker
origin **after** authenticating — a convincing post-login phishing vector.
`new URL("https://evil.com", base)` resolves to `https://evil.com/`, and
`//evil.com` also escapes the origin. The session cookies are HttpOnly so the
session itself isn't handed over, but the destination page is fully
attacker-controlled. The fix is to accept only same-origin internal paths.

## Current state

- `apps/web/app/auth/callback/route.ts:7` reads the param and `:24` redirects
  to it unvalidated:
  ```ts
  const next = url.searchParams.get("next") ?? "/today";
  // ...
  if (!error) {
    return NextResponse.redirect(new URL(next, baseUrl));
  }
  ```
- `apps/web/app/sign-in/page.tsx:15` derives `nextParam` and threads it into
  three sinks:
  ```ts
  const nextParam = searchParams.get("next") ?? "/today";
  // :45  redirectTo: `${origin}/auth/callback?next=${encodeURIComponent(nextParam)}`
  // :73  router.replace(nextParam as never);
  // :86  emailRedirectTo: `${origin}/auth/callback?next=${encodeURIComponent(nextParam)}`
  ```
  The dangerous sink here is `:73` `router.replace(nextParam as never)` (a
  direct client-side navigation to an unvalidated value). Lines 45/86 embed it
  back into a `?next=` that the callback route consumes — so sanitizing at the
  callback closes those too, but sanitizing at the source is defense in depth.

- There is no existing URL-safety helper for *paths*; the existing
  `apps/web/lib/safe-url.ts` `safeHref` guards external `https?://` links
  (a different job). Add a small local helper rather than reusing that one.

## Commands you will need

| Purpose    | Command                                            | Expected on success |
|------------|----------------------------------------------------|---------------------|
| Typecheck  | `cd apps/web && pnpm typecheck`                    | exit 0, no errors   |
| Lint       | `cd apps/web && pnpm lint`                         | exit 0              |
| Unit tests | `cd apps/web && pnpm run test`                     | all pass            |
| Build      | `cd apps/web && pnpm build`                        | build succeeds      |

> `pnpm build` is mandatory here per repo policy (`CLAUDE.md` Pre-PR
> checklist) because this touches App-Router routing and `useSearchParams`.

## Scope

**In scope**:
- `apps/web/app/auth/callback/route.ts`
- `apps/web/app/sign-in/page.tsx`
- `apps/web/lib/safe-url.ts` (add a `safeNextPath` helper) — OR a new tiny
  module `apps/web/lib/safe-next.ts`; prefer adding to `safe-url.ts` to keep
  URL-safety logic in one place.
- `apps/web/lib/safe-url.test.ts` (add tests for the new helper)

**Out of scope**:
- The Supabase client setup, middleware, `AppAccessGate` — unrelated.
- The existing `safeHref`/`socialHref` functions — do not change their
  behavior; only ADD a new helper.

## Git workflow

- Branch: `advisor/019-block-open-redirect`
- Commit style: `fix(web): reject non-local next param in auth redirect (open redirect)`
- Do NOT push or open a PR unless the operator asks.

## Steps

### Step 1: Add a `safeNextPath` helper

In `apps/web/lib/safe-url.ts`, add:
```ts
/**
 * Returns `candidate` only if it is a safe same-origin internal path
 * (starts with a single "/", not "//" and not "/\"). Otherwise returns the
 * fallback. Prevents open-redirect via an absolute or protocol-relative URL.
 */
export function safeNextPath(candidate: string | null | undefined, fallback = "/today"): string {
  if (!candidate) return fallback;
  if (!candidate.startsWith("/")) return fallback;      // reject absolute (https://…) and relative
  if (candidate.startsWith("//") || candidate.startsWith("/\\")) return fallback; // reject protocol-relative
  return candidate;
}
```

**Verify**: `cd apps/web && pnpm typecheck` → exit 0.

### Step 2: Use it in the callback route

In `apps/web/app/auth/callback/route.ts`, wrap the param read:
```ts
import { safeNextPath } from "@/lib/safe-url";
// ...
const next = safeNextPath(url.searchParams.get("next"));
```
Leave the rest (`new URL(next, baseUrl)`) as-is — `next` is now guaranteed to
be an internal path.

**Verify**: `cd apps/web && pnpm typecheck` → exit 0.

### Step 3: Use it in the sign-in page

In `apps/web/app/sign-in/page.tsx`, change the derivation at `:15`:
```ts
const nextParam = safeNextPath(searchParams.get("next"));
```
(Add the import.) This makes `router.replace(nextParam as never)` at `:73` and
the two `?next=` embeds at `:45,86` all use the sanitized value.

**Verify**: `cd apps/web && pnpm typecheck && pnpm lint` → exit 0.

### Step 4: Tests

In `apps/web/lib/safe-url.test.ts`, add a `describe("safeNextPath")` block
covering: `/today` → `/today`; `/leads/123?x=1` → unchanged;
`https://evil.com` → `/today`; `//evil.com` → `/today`; `/\evil.com` →
`/today`; `null`/`undefined`/`""` → `/today`; a custom fallback is honored.

**Verify**: `cd apps/web && pnpm run test` → all pass including the new block.

### Step 5: Build gate

**Verify**: `cd apps/web && pnpm build` → build succeeds (no typed-route or
Suspense errors).

## Test plan

- New tests in `apps/web/lib/safe-url.test.ts` under `safeNextPath`: the seven
  cases in Step 4 (internal path passthrough, query preserved, absolute URL
  rejected, protocol-relative rejected, backslash-tricks rejected, empty →
  fallback, custom fallback).
- Structural pattern: the existing `describe` blocks in the same file.
- Verification: `pnpm run test` → all pass.

## Done criteria

- [ ] `pnpm typecheck` exits 0
- [ ] `pnpm lint` exits 0
- [ ] `pnpm run test` passes; new `safeNextPath` tests exist and pass
- [ ] `pnpm build` succeeds
- [ ] `grep -n "searchParams.get(\"next\")" apps/web/app/sign-in/page.tsx apps/web/app/auth/callback/route.ts` shows both wrapped in `safeNextPath`
- [ ] No files outside the in-scope list modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- The `route.ts` / `sign-in/page.tsx` excerpts don't match live code (drift).
- `pnpm build` fails for a reason unrelated to this change (pre-existing
  breakage) — report it; do not try to fix unrelated build errors here.

## Maintenance notes

- Any future place that reads a redirect target from user input (query, form,
  postMessage) must pass it through `safeNextPath` (or an allowlist). Reviewer
  should grep for new `router.replace(`/`redirect(` calls fed by params.
- If deep-link `next` targets ever need to include an absolute URL to a known
  sibling domain, switch from the path check to an explicit origin allowlist —
  do NOT relax `safeNextPath` to accept arbitrary absolute URLs.
