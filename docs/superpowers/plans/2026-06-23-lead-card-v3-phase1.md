# Lead card v3 — Phase 1 (two-pane layout) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (the tasks are tightly coupled around `LeadCard`/`UnifiedFeed`, so inline execution — not parallel subagents — is correct). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the tab-centric lead card into a two-pane card — key info always visible on the left, activity (composer-on-top) on the right — and remove Блейк from the card flow.

**Architecture:** `LeadCard` becomes header + stage stepper + a two-column grid. The left column composes always-visible info (summary, next step, deal params, primary contact, source, custom fields). The right column holds the composer at the top and a tab switcher (Активность default · Задачи · Контакты · КП · Заметки · Архив). Composer mode/seed state lifts from `UnifiedFeed` to `LeadCard` so the left-column «Следующий шаг» can drive the right-column composer.

**Tech Stack:** Next.js 15 App Router, React, TypeScript strict, Tailwind, TanStack Query. No new deps.

## Global Constraints

- Design system only: brand-* tokens, Manrope font, **no Inter/Roboto/Arial**, spacing scale **4-8-12-16-24-32** (lint rule `drinkx/no-arbitrary-px` — no `[Npx]`).
- Mobile-first; the two columns must stack to one column on small screens.
- Preserve `?tab=` deep-linking for the right-column tabs.
- Pre-PR checks: `npm run typecheck`, `npm run lint` (0 errors), `pnpm build` (mandatory — `useSearchParams`/Suspense).
- Reuse existing components/hooks; do not add backend.
- Apply the `make-interfaces-feel-better` skill for polish (hover/focus, optical alignment, spacing rhythm).

---

## File structure

- `feed/FeedComposer.tsx` — modify: remove `@Блейк` routing + hint (Task 1).
- `LeadInfoBlock.tsx` — modify: remove the `AIBriefSection` + enrichment imports/usage (Task 2).
- `feed/UnifiedFeed.tsx` — modify: drop the in-feed `NextStepBanner` and the bottom composer; accept the composer as a sibling controlled by the parent; expose feed `items` upward OR keep self-fetching and let the parent also read `useFeed` (cached). Composer moves to the right-pane top (Task 4).
- New `LeadLeftColumn.tsx` — the always-visible info column (Task 3).
- New `PrimaryContactCard.tsx` — primary-contact summary for the left column (Task 3).
- `LeadCard.tsx` — modify: two-pane grid; lift composer mode/seed state; tab set; remove «Информация» (Task 4).
- Removed usage: `DealAndAITab.tsx` (its pieces — `LeadInfoBlock`, `SourceSection` — render in the left column; the file can be deleted once unreferenced).

---

## Task 1: Remove Блейк from the composer

**Files:**
- Modify: `apps/web/components/lead-card/feed/FeedComposer.tsx`

- [ ] **Step 1: Read the file** and locate (a) the `@Блейк` start-of-text detection (~line 84, used in the `comment` submit branch ~line 97), the `ai_suggestion` POST it triggers, and (b) the placeholder string `"Написать комментарий или @Блейк..."` (~line 188-189).

- [ ] **Step 2: Remove the AI route.** In the `comment` submit branch, delete the `@Блейк`-prefix check and the branch that POSTs an `ai_suggestion`/asks Blake. A comment submit always posts a plain `comment` activity now. Remove the now-unused `seed`-as-`@Блейк` handling only if `seed` is no longer used (keep `seed`/`onSeedConsumed` if other callers still pass it — verify; the `FeedItemAI` «Спросить подробнее» seed becomes dead once AI items stop being produced, but keep the prop wiring to avoid breaking the interface in this task).

- [ ] **Step 3: Fix the placeholder.** Change `"Написать комментарий или @Блейк..."` → `"Написать комментарий…"`.

- [ ] **Step 4: Verify**

Run: `cd apps/web && npm run typecheck && npx eslint "components/lead-card/feed/FeedComposer.tsx"`
Expected: typecheck passes; eslint 0 errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/lead-card/feed/FeedComposer.tsx
git commit -m "feat(lead-card): drop @Блейк from the activity composer"
```

---

## Task 2: Remove the AI Бриф (enrichment) from LeadInfoBlock

> Per the approved spec, AI leaves the card flow. `AIBriefSection` is the enrichment research block; removing it also removes the in-card enrichment trigger — that is an accepted consequence (flag in the PR; enrichment can get a home elsewhere later).

**Files:**
- Modify: `apps/web/components/lead-card/LeadInfoBlock.tsx`

- [ ] **Step 1: Read the file.** Identify: the `useLatestEnrichment`/`useTriggerEnrichment` import (~line 26), the `ai`/enrichment data wiring inside the component, the `<AIBriefSection lead={lead} ai={ai} />` render (~line 244-245), and the whole `function AIBriefSection(...)` definition (~line 448 to its close).

- [ ] **Step 2: Remove the render** — delete the `{/* Collapsible … AI Бриф */}` comment + `<AIBriefSection .../>` line.

- [ ] **Step 3: Remove the component** — delete the entire `AIBriefSection` function.

- [ ] **Step 4: Remove now-dead code** — the `useLatestEnrichment`/`useTriggerEnrichment` import and any `ai`/`run`/enrichment local state that only fed `AIBriefSection`. Keep everything that drives the deal-params table.

- [ ] **Step 5: Verify**

Run: `cd apps/web && npm run typecheck && npx eslint "components/lead-card/LeadInfoBlock.tsx"`
Expected: typecheck passes (no unused-import / undefined-symbol errors); eslint 0 errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/lead-card/LeadInfoBlock.tsx
git commit -m "feat(lead-card): remove AI Бриф block from the deal-info panel"
```

---

## Task 3: Left column — `PrimaryContactCard` + `LeadLeftColumn`

**Files:**
- Create: `apps/web/components/lead-card/PrimaryContactCard.tsx`
- Create: `apps/web/components/lead-card/LeadLeftColumn.tsx`

**Interfaces:**
- `PrimaryContactCard` — Consumes `{ lead: LeadOut }`. Reads `useContacts(lead.id)`, finds `lead.primary_contact_id` (fallback: first contact). Renders avatar + name + role + call/email/telegram links + «ещё N контактов». Produces: a self-contained card; no outward API.
- `LeadLeftColumn` — Consumes `{ lead: LeadOut; items: FeedItemOut[]; onCreateTaskRequest: () => void }`. Produces: the assembled always-visible column. `items`/`onCreateTaskRequest` are forwarded to the reused `NextStepBanner`.

- [ ] **Step 1: Write `PrimaryContactCard.tsx`.** Reuse the avatar/initials/role-label patterns from `ContactsTab.tsx` (`initialsOf`, `colorFor`, `ROLE_LABELS`) and `safeHref` for tel/mailto/telegram. Card chrome: `rounded-card border border-brand-border bg-white p-4`. Show the primary contact (or first contact); if none, a muted «Контакт не указан» + a link to the Контакты tab. Include a «ещё N контактов» link when `contacts.length > 1`.

- [ ] **Step 2: Write `LeadLeftColumn.tsx`,** composing in this order, each in its own card/section:
  1. **Сводка** — priority badge (reuse `Badge`), segment label, `lead.deal_amount` large (reuse the `formatRub` pattern from `LeadInfoBlock`).
  2. **Следующий шаг** — `<NextStepBanner items={items} onCreateTaskRequest={onCreateTaskRequest} />` (existing component, reused as-is).
  3. **Параметры сделки** — `<LeadInfoBlock lead={lead} />` (now without the AI brief).
  4. **Контакт** — `<PrimaryContactCard lead={lead} />`.
  5. **Источник** — `<SourceSection lead={lead} />` (renders only for form-sourced leads).
  6. **Доп. поля** — `<CustomFieldsPanel leadId={lead.id} />` (renders only when custom fields exist).

  Wrap in `<div className="space-y-4">`.

- [ ] **Step 3: Verify**

Run: `cd apps/web && npm run typecheck && npx eslint "components/lead-card/PrimaryContactCard.tsx" "components/lead-card/LeadLeftColumn.tsx"`
Expected: typecheck passes; eslint 0 errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/lead-card/PrimaryContactCard.tsx apps/web/components/lead-card/LeadLeftColumn.tsx
git commit -m "feat(lead-card): left-column components (summary, next step, contact)"
```

---

## Task 4: Two-pane `LeadCard` + composer-on-top `UnifiedFeed`

**Files:**
- Modify: `apps/web/components/lead-card/feed/UnifiedFeed.tsx`
- Modify: `apps/web/components/lead-card/LeadCard.tsx`

**Interfaces:**
- `UnifiedFeed` — change Consumes to `{ leadId: string; composerSeed?: string; onComposerSeedConsumed?: () => void; composerModeRequest?: "comment"|"task"|"call"|"file"|null; onComposerModeRequestConsumed?: () => void }`. Remove the internal `<NextStepBanner>` (it moves to the left column) and render `<FeedComposer>` at the TOP (before the items list) instead of the bottom. Composer state is now owned by the parent and passed through.
- `LeadCard` — owns `composerSeed`/`composerModeRequest` state and the feed `items` (via `useFeed(leadId)`, cached — `UnifiedFeed` also calls `useFeed`, same cache key, no double fetch). Passes `items` + `onCreateTaskRequest={() => setComposerModeRequest("task")}` to `LeadLeftColumn`, and the composer state to `UnifiedFeed`.

- [ ] **Step 1: `UnifiedFeed` — lift composer state + move composer to top.** Replace the internal `composerSeed`/`composerModeRequest` `useState` with props (listed above). Delete the `<NextStepBanner …/>` block. Move `<FeedComposer … />` from the bottom to the top of the returned tree (above the items `space-y-3` block). Keep `useFeed`, the email modal, and `FeedItemSwitch` unchanged. `onAskFollowUp` (AI follow-up seed) becomes dead once AI items stop — keep the wiring, it is harmless.

- [ ] **Step 2: `LeadCard` — lift state + read feed items.** Add `const [composerSeed, setComposerSeed] = useState<string>()` and `const [composerModeRequest, setComposerModeRequest] = useState<…|null>(null)`. Add `const feed = useFeed(lead.id)` and flatten `items` (mirror `UnifiedFeed`'s `useMemo` flatten). The existing `useFeed(leadId)` for `mergedFromCount` already exists — reuse it; just also derive `items`.

- [ ] **Step 3: `LeadCard` — two-pane body.** Replace the current single-column tab body with:
  - Keep header (`LeadCardHeader`) + `StagesStepper` as-is.
  - Body grid: `<div className="... grid md:grid-cols-[320px_minmax(0,1fr)] gap-4 md:gap-6">`.
    - Left: `<LeadLeftColumn lead={lead} items={items} onCreateTaskRequest={() => setComposerModeRequest("task")} />` — wrap in a `md:sticky md:top-[...]` container using an existing scroll-offset token (reuse the value `StagesStepper`/header use; if none on the scale, use a Tailwind named class like `md:top-24`, NOT an arbitrary `[Npx]`).
    - Right: the tab switcher + `TabsContent`. Set the default tab to `activity`.
  - On mobile the grid collapses to one column (left first, then right) — `grid` with a single column by default, `md:grid-cols-[...]` for two.

- [ ] **Step 4: `LeadCard` — tab set.** Update `TabKey` and `TABS`: remove `"deal-ai"` (Информация); ensure tabs = `activity` · `tasks` (Задачи) · `contacts` (Контакты) · `quote` (КП) · `notes` (Заметки) · `archive`. Remove the `DealAndAITab` import and its `<TabsContent value="deal-ai">`. Wire `<TabsContent value="activity"><UnifiedFeed leadId={lead.id} composerSeed={composerSeed} onComposerSeedConsumed={() => setComposerSeed(undefined)} composerModeRequest={composerModeRequest} onComposerModeRequestConsumed={() => setComposerModeRequest(null)} /></TabsContent>`.

- [ ] **Step 5: Remove the old right-column `CustomFieldsPanel`** mount (it now lives in `LeadLeftColumn`); delete the now-unused `DealAndAITab.tsx` file.

- [ ] **Step 6: Verify**

Run: `cd apps/web && npm run typecheck && npm run lint`
Expected: typecheck passes; lint 0 errors (pre-existing arbitrary-px warnings elsewhere are fine; introduce none).

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/lead-card/feed/UnifiedFeed.tsx apps/web/components/lead-card/LeadCard.tsx
git rm apps/web/components/lead-card/DealAndAITab.tsx
git commit -m "feat(lead-card): two-pane layout — info left, activity (composer top) right"
```

---

## Task 5: Build + manual verification

- [ ] **Step 1: Full build**

Run: `cd apps/web && pnpm build`
Expected: «✓ Compiled successfully», `/leads/[id]` compiles, typedRoutes pass.

- [ ] **Step 2: Manual checklist (on a real lead, admin/manager):**
  - Left column shows summary, next step (real task or «поставить задачу»), deal params (no AI brief), primary contact, source (if form lead), custom fields (if any).
  - Clicking «поставить задачу как следующий шаг» (left) focuses the right composer in task mode.
  - Right composer is at the top; modes Дело/Задача · Комментарий work; no «@Блейк».
  - Switching right tabs (Задачи/Контакты/КП/Заметки/Архив) leaves the left column unchanged.
  - Inline-editing a deal param still saves.
  - Mobile (narrow): columns stack, left first; nothing overflows.
  - `?tab=quote` deep-link opens the КП tab.

- [ ] **Step 3: Commit any polish fixes**, then open the PR for review.

---

## Self-review notes

- **Spec coverage:** two-pane layout (Task 4), left-column order (Task 3), composer-on-top + Блейк removal (Tasks 1, 4), «Информация» folded in (Task 4), AI brief removed (Task 2), mobile stack (Task 4), `?tab=` preserved (Task 4). Phase 2 (close prompt) is a separate plan.
- **Reuse over rebuild:** `NextStepBanner` (next step), `LeadInfoBlock` (params), `ContactsTab` patterns (`PrimaryContactCard`), `SourceSection`, `CustomFieldsPanel` — all existing.
- **Risk:** the cross-column composer trigger (left «поставить задачу» → right composer) relies on lifting composer state to `LeadCard` (Task 4 Steps 1-2). Verified the existing `modeRequest`/`onModeRequestConsumed` props on `FeedComposer` already support this.
- **Consequence flagged:** removing `AIBriefSection` also removes the in-card enrichment trigger — call out in the PR.
