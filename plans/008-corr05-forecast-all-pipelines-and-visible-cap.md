# Plan 008: Make Forecast count all pipelines and stop silently truncating at 500 leads

> **Executor instructions**: Follow step by step; run every verification command.
> On any "STOP conditions" item, stop and report. Update this plan's row in
> `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat a81462c..HEAD -- "apps/web/app/(app)/forecast/page.tsx"`
> If it changed, compare against "Current state"; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `a81462c`, 2026-06-20

## Why this matters

The Forecast page is the headline revenue KPI, but it computes two wrong numbers silently:
1. It reads stages from **only the first pipeline** (`pipelines?.[0]?.stages`). In any workspace with more than one pipeline, every lead on pipelines 2+ fails the `stageById` lookup, gets `stage = null`, and is silently dropped from pipeline total, weighted forecast, at-risk, and the funnel chart.
2. It fetches at most **500 leads** (`page_size: 500`) and sums only those, with no indication the total is partial — so a workspace with >500 active leads sees an under-counted forecast that looks authoritative.

A forecast that quietly lies is worse than no forecast. This plan fixes the multi-pipeline correctness bug and makes any truncation visible. (Moving the weighting server-side is a larger, separate plan — see Maintenance notes.)

## Current state

`apps/web/app/(app)/forecast/page.tsx` (client component), as of `a81462c`:

```tsx
// line 19
const FORECAST_LEADS_FILTER = { page_size: 500 } as const;
...
// line 36 — only the FIRST pipeline's stages are mapped
const stages = pipelines?.[0]?.stages ?? [];
const stageById = new Map(stages.map((s) => [s.id, s]));
const leads = leadsData?.items ?? [];
...
// line 72-90 — every lead is priced via stageById.get(lead.stage_id)
for (const lead of leads) {
  const amount = Number(lead.deal_amount ?? 0);
  const stage = lead.stage_id ? stageById.get(lead.stage_id) : null;
  if (lead.assignment_status === "assigned" && stage && !stage.is_won && !stage.is_lost) {
    pipelineTotal += amount;
    weightedTotal += (amount * (stage.probability ?? 0)) / 100;
    ...
  }
}
```

- `stages` is used twice: to build `stageById` (line 37) and to seed `stageBarMap` (the `stages.filter((s) => !s.is_won && !s.is_lost)` block around line 56). Both must see all pipelines' stages.
- Stage `id`s are UUIDs (globally unique across pipelines), so flattening into one map is safe — no key collisions.
- `usePipelines()` returns an array of pipelines, each with a `stages` array (see `apps/web/lib/hooks/use-pipelines.ts`).
- `useLeads(FORECAST_LEADS_FILTER)` returns `{ items, total }` — `leadsData.total` is the true count; `items.length` is what was fetched (≤500).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Typecheck | `cd apps/web && npm run typecheck` | exit 0 |
| Lint | `cd apps/web && npm run lint` | exit 0, no new errors |
| Build | `cd apps/web && pnpm build` | exit 0; `/forecast` in the route table |

(Per repo `CLAUDE.md`, `pnpm build` is mandatory for App-Router pages — tsc alone is not enough.)

## Scope

**In scope:**
- `apps/web/app/(app)/forecast/page.tsx` only.

**Out of scope (do NOT touch):**
- Backend — no new endpoint in this plan (server-side forecast is a separate, larger plan).
- The chart components in `apps/web/components/ui/Chart`.
- The `useLeads` hook and its pagination.

## Git workflow

- Branch: `advisor/008-forecast-all-pipelines`
- Commit e.g. `fix(forecast): aggregate across all pipelines; surface lead-cap truncation`.
- Do NOT push/PR unless instructed.

## Steps

### Step 1: Flatten stages across all pipelines

Replace the single-pipeline stage source so both `stageById` and the stage-bar seed see every pipeline's stages:

```tsx
const stages = (pipelines ?? []).flatMap((p) => p.stages ?? []);
```

Leave `stageById` and the `stages.filter(...)` stage-bar seed as-is — they now operate over all stages. Confirm there is no remaining `pipelines?.[0]` / `pipelines[0]` reference in the file.

**Verify**: `grep -n "pipelines?\.\[0\]\|pipelines\[0\]" apps/web/app/\(app\)/forecast/page.tsx` → no match.

### Step 2: Surface truncation instead of hiding it

Where the page renders the forecast summary, add a visible note when the fetched leads are capped — i.e. when `leadsData.total > leadsData.items.length` (equivalently `> 500`). Render a small caption near the pipeline/weighted totals, e.g. "Показаны первые 500 из {total} лидов — суммы частичные". Use the page's existing caption/muted text style (`C` from `@/lib/design-system`). Do not change the math; just make the partiality visible.

**Verify**: `cd apps/web && npm run typecheck` → exit 0. Read the diff: a conditional caption referencing `leadsData.total` exists.

### Step 3: Build

**Verify**: `cd apps/web && npm run lint && pnpm build` → both exit 0; `/forecast` appears in the build route output.

## Test plan

- This page has no unit-test harness; verification is typecheck + lint + production build (the App-Router gate that catches the real failures here).
- Manual (if a dev server is available): in a workspace with ≥2 pipelines, leads on the second pipeline now contribute to the totals; with >500 active leads the truncation caption appears.

## Done criteria

- [ ] `grep -n "pipelines?\.\[0\]\|pipelines\[0\]" "apps/web/app/(app)/forecast/page.tsx"` → no match
- [ ] A truncation caption keyed off `leadsData.total` exists in the file
- [ ] `cd apps/web && npm run typecheck` exits 0
- [ ] `cd apps/web && npm run lint` exits 0 (no new errors)
- [ ] `cd apps/web && pnpm build` exits 0
- [ ] No files outside `forecast/page.tsx` modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report if:
- "Current state" excerpts don't match live code (drift).
- `usePipelines()` returns a shape without `.stages` per pipeline (then the flatten is wrong — report).
- The product wants the forecast scoped to ONE selected pipeline (a picker) rather than summed across all — that's a UX decision; report instead of guessing.

## Maintenance notes

- The real fix is a **server-side forecast endpoint** (weighted sum grouped by pipeline/stage/owner, scoped like `GET /leads`) so the number is consistent across the forecast page, manager dashboard, and the daily digest, and isn't recomputed in the browser over a capped lead dump. That is a separate L-effort plan (the `quotas` table comment already anticipates pipeline-coverage/forecast-accuracy). This plan is the stop-the-bleeding client fix.
- Reviewer: confirm UUID stage ids really are unique across pipelines (they are in this schema) so the flat map has no collisions.
