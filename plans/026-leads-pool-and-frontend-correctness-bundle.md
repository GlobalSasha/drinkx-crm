# Plan 026: Frontend correctness bundle — pool truncation, claim rollback, toast keys, 401 recovery

> **Executor instructions**: Four independent sub-fixes (A–D). Do them in any
> order; each is separately verifiable. Fix A has an open decision — read its
> note first. Run every verification command. Honor STOP conditions. Update
> this plan's row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/web/app/(app)/leads-pool/page.tsx apps/web/lib/hooks/use-leads.ts apps/web/components/layout/AppAccessGate.tsx apps/web/components/leads-pool/PoolRow.tsx`
> Compare against "Current state"; on a mismatch for a given fix, STOP that fix.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (A is MED — needs a decision)
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

Four frontend correctness issues found in the round-4 delta:

- **(A) Silent pool truncation.** The leads pool fetches `page_size: 500` once
  and filters client-side; every count (header total, per-chip city/segment/
  tier counts, Export count) is computed off that single page. Once the pool
  exceeds the returned page, leads beyond it are invisible and every count is
  wrong — managers silently work a partial pool.
- **(B) Concurrent-claim rollback resurrects a claimed lead.** `onError`
  restores a whole-cache snapshot taken at mutate time; if two claims overlap
  and one 409s, its rollback writes back a snapshot that still contains the
  lead the OTHER claim already removed — the gone lead reappears as claimable
  until the next refetch.
- **(C) Toast keys use `Date.now()`.** Two toasts in the same millisecond get
  identical React keys and the dismissal filter can drop both at once.
- **(D) No path back to sign-in on a backend 401.** `AppAccessGate` special-
  cases only the invite-required 403; a persistent 401 (backend JWT expired
  while the middleware still sees a cookie) lands the user on a dead
  "Повторить" error card with no way to re-authenticate.

## Current state

- `apps/web/app/(app)/leads-pool/page.tsx:85-98`:
  ```tsx
  const addToast = useCallback((message, type = "success") => {
    const id = Date.now();                    // (C) collision-prone key
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);
  // ...
  const poolQuery = usePoolLeads({ page_size: 500, form_id: formId, needs_review: needsReview }); // (A)
  ```
  The `id` is also used as the React `key` when rendering toasts (≈ line 460).
- `apps/web/lib/hooks/use-leads.ts:215-249` — `useClaimLead`:
  `onMutate` snapshots ALL `["leads-pool"]` caches and removes the lead;
  `onError` (`:234-239`) restores each snapshot wholesale; `onSettled`
  (`:246-248`) invalidates `["leads-pool"]`. The whole-snapshot restore is the
  (B) bug.
- `apps/web/components/leads-pool/PoolRow.tsx` — renders a `claiming` state
  (opacity + spinner) that (per the frontend audit) is effectively dead because
  `onMutate` removes the row from the cache before it can render. This is a
  minor cleanup, folded into (B)'s review, not a separate required fix.
- `apps/web/components/layout/AppAccessGate.tsx:26,48-68` — only a 403 with
  `code: "invite_required"` triggers sign-out+redirect; any other error
  (including 401) falls to the generic retry card.
  `apps/web/lib/hooks/use-me.ts:21-22` retries non-403 errors.

## Commands you will need

| Purpose    | Command                          | Expected on success |
|------------|----------------------------------|---------------------|
| Typecheck  | `cd apps/web && pnpm typecheck`  | exit 0              |
| Lint       | `cd apps/web && pnpm lint`       | exit 0              |
| Unit tests | `cd apps/web && pnpm run test`   | all pass            |
| Build      | `cd apps/web && pnpm build`      | build succeeds      |

## Scope

**In scope**:
- `apps/web/app/(app)/leads-pool/page.tsx` (C, and A if pursued)
- `apps/web/lib/hooks/use-leads.ts` (B)
- `apps/web/components/layout/AppAccessGate.tsx` (D)
- `apps/web/components/leads-pool/PoolRow.tsx` (optional cleanup with B)
- Test files alongside the above

**Out of scope**:
- Backend pagination API changes (A may need them — see its note).
- The claim endpoint itself.
- Restyling; this is behavior only.

## Steps

### Fix C — stable toast keys (smallest, do first)

Replace `Date.now()` with a monotonic counter ref or `crypto.randomUUID()`:
```tsx
const toastSeq = useRef(0);
// inside addToast:
const id = toastSeq.current++;         // or crypto.randomUUID()
```
Keep `id` as both the state id and the React key.

**Verify**: `pnpm typecheck && pnpm run test` → pass.

### Fix B — per-id claim rollback (not whole-snapshot)

In `useClaimLead`, change `onError` to re-insert only the failed `leadId`
instead of restoring the entire pre-mutation snapshot. Simplest robust
approach: drop the manual snapshot/restore entirely and rely on the existing
`onSettled` invalidation of `["leads-pool"]` to reconcile — the pool refetches
and shows the true state. If you keep an optimistic remove for snappiness, then
on error re-add only that lead to each cache (dedupe by id) rather than
overwriting the cache. Do NOT restore a stale full snapshot.

**Verify**: `pnpm typecheck` → exit 0. Add a hook test if the harness has
QueryClient test utilities; otherwise verify by reasoning + the invalidation
path and note that a full integration test is deferred (frontend test baseline
is DEBT-1). Optionally remove the now-dead `claiming`/`claimingIds` UI in
`PoolRow.tsx` + `page.tsx` if you confirm it never renders (STOP-check: only
remove if a grep shows it's truly unreachable).

### Fix D — recover from a backend 401

In `AppAccessGate.tsx`, extend the special-case: if `me.error` is an `ApiError`
with `status === 401`, sign out and `router.replace("/sign-in")` (same handling
as the invite case), instead of showing the retry card. Also consider making
`use-me.ts` not retry on 401 (like it already skips retry on 403) so the
redirect happens promptly.

**Verify**: `pnpm typecheck && pnpm lint` → exit 0.

### Fix A — pool truncation (DECISION REQUIRED)

Open question: keep client-side per-chip counts (current UX the code comment
defends) vs move filtering + facet counts server-side. Do NOT silently rewrite
the UX. Minimum acceptable fix without a backend change: when
`poolQuery.data.total > allItems.length`, render a visible banner
("Показаны первые N из M — уточните фильтр") so managers know the view is
partial. The full fix (server-side filter + facet counts, or
`useInfiniteQuery`) needs a product/backend decision — record it and, if not
decided, ship only the banner.

**Verify**: `pnpm typecheck && pnpm run test && pnpm build` → pass.

## Test plan

- Fix C: a unit test that two `addToast` calls produce distinct ids/keys.
- Fix B: if QueryClient test utils exist, a test that an errored claim among
  two doesn't resurrect the other's removed lead; else documented as
  deferred (DEBT-1).
- Fix D: a test (or documented manual check) that a 401 from `/auth/me` routes
  to `/sign-in`.
- Fix A: a test that the truncation banner shows when `total > items.length`.
- Pattern: existing tests under `apps/web` (e.g. `lib/safe-url.test.ts`,
  `components/lead-card/LeadCardHeader.test.tsx`).

## Done criteria

- [ ] `pnpm typecheck` exits 0
- [ ] `pnpm lint` exits 0
- [ ] `pnpm run test` passes (new toast-key test at minimum)
- [ ] `pnpm build` succeeds
- [ ] `grep -n "Date.now()" apps/web/app/(app)/leads-pool/page.tsx` no longer used as a key/id
- [ ] Fix B no longer restores a full snapshot in `onError`
- [ ] Fix D routes a 401 to `/sign-in`
- [ ] Fix A: banner present, OR the decision to do the full server-side fix is recorded
- [ ] No files outside the in-scope list modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- Any target excerpt doesn't match live code (drift) — skip that sub-fix and
  report.
- Fix A's full server-side approach is chosen — that needs a backend
  pagination/facet endpoint; STOP and split it into a backend plan first.
- Removing the `claiming` UI turns out to be reachable (grep shows it renders)
  — leave it; don't delete live UI.

## Maintenance notes

- Fix A's banner is a stopgap; the real fix is server-side filtering + facet
  counts once the pool reliably exceeds the page size.
- Reviewer: confirm B's rollback can't resurrect a lead, and D actually signs
  out (clears the Supabase session) before redirecting, not just navigates.
