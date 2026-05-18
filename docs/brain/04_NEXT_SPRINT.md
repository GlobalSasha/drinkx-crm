# Sprint 3.5 — Production Polish v2

**Status:** 🟡 IN PROGRESS
**Started:** 2026-05-18
**Source:** v0.app production audit (browser walk of 12 screens via test user)
**Audit artefacts:** `~/Downloads/crm-ui-ux-analysis (4)/` (18 screenshots + `audit-production.tsx`)

The Sprint-3.5 «Inbox follow-ups» / Sprint-3.2 «Lead AI Agent polish» / soft-launch
options that were parked in this file are still valid — they're tracked in
`02_ROADMAP.md` and the prior `04_NEXT_SPRINT.md` history is in git. Production
polish jumped the queue because v0 surfaced concrete UX gaps that we couldn't
see from inside the project.

---

## Why this sprint

v0 walked the real production app for the first time (previous attempts ended up
on `globalsasha.github.io/drinkx-crm-prototype`). Findings are concrete, sourced
from screenshots of real UI text. Scope below = only items that are NOT
already-shipped according to `00_CURRENT_STATE.md`.

Drops we don't take from the audit:
- "Sidebar uses emoji" — false (already Lucide; the 🧪 in test-login is intentional).
- "Inbox is a stub" — false (Sprint 3.4 closed this).
- "No mobile layout" — false (Sprint 1.5 closed this).
- "No global search" — false (`GlobalSearch.tsx` + ⌘K).
- "Pipeline columns don't scroll" — false (already fixed).

Data-quality issues (FIT SCORE "—" on 200+ leads, all /today tasks at 09:00,
city "НЕ УКАЗАН" on AI-briefed leads) are NOT scoped here — they're backend /
seed-data work and belong in a separate backfill ticket.

---

## Scope (gated)

### G1 — Day-1 quick wins

- [x] `/knowledge` — replace bare "Раздел в разработке." with a roadmap-style
      placeholder (icon, title, 2 lines of what will land, soft «Уведомить меня»
      disabled hint). File: `apps/web/app/(app)/knowledge/page.tsx`.
- [x] `/team` redirect — managers currently get a silent
      `router.replace("/today")`. Replace with an explicit empty-state
      ("Раздел доступен руководителям") + a back link, so URL-typing the page
      doesn't feel like the app is broken. File: `apps/web/app/(app)/team/page.tsx`.
- [x] Pipeline card segment-tag overflow — long segment names truncate to
      "ПРОДУКТОВЫ…" at 1440px. Add a short-alias map (`продуктовый ритейл` →
      `ПРОД.`, `кофейни` → `КОФЕ`, `АЗС` → `АЗС`, `QSR` → `QSR`, etc.) and use
      it in the kanban card render.
- [x] Lead Card → «Сделка и AI» — change «СУММА СДЕЛКИ НЕ УКАЗАНА — ПОЛЕ
      ПОЯВИТСЯ ПОСЛЕ ИНТЕГРАЦИИ CRM-ФОРМЫ СУММЫ» to neutral "Не указана"
      (or an inline edit affordance). Current copy reads like an integration
      error.
- [x] Sidebar inbox badge consistency — sidebar caps at "99+" while the
      `/inbox` page shows the real number (e.g. "864 ожидают"). Bump the
      sidebar cap to "999+" (or show the real count). File:
      `apps/web/components/layout/SidebarNav.tsx`.

### G2 — Pipeline card: surface score + tier  ❌ DROPPED (2026-05-18)

The v0 audit suggested adding Tier (A/B/C) + Score back to the kanban card,
arguing the data exists in `/leads-pool` but isn't surfaced here. However,
`PipelineLeadCard.tsx` carries an explicit header comment from the Lead Card
Redesign sprint:

> «Removed from the previous design (intentionally): priority badge, score,
> fit_score, rotting indicators. The pipeline view is now a pure who/what/when
> surface; AI and rotting metadata live in the Lead Card detail view.»

Decision: keep the kanban surface pure. AI metadata lives in the detail view
on purpose. Empty-state per pipeline column also dropped — pipelines with
many empty stages is a configuration choice, not a UX bug. Revisit if user
feedback contradicts.

### G3 — Activity Feed v2

- [x] AI block styling — `FeedItemAI` now uses a Sparkles icon (was Bot)
      and the inner card has a 3px brand-accent left border on top of the
      existing soft tint, so Чак's messages read as a distinct "AI" voice
      next to manager comments.
- [x] Inbox → Activity auto-link — `message_services.receive` already
      writes an Activity row when an inbound webhook matches a lead
      (Sprint 3.4). The actual gap was on the frontend: `UnifiedFeed`'s
      switch had no `case "telegram":` / `case "max":`, so those rows
      fell through to the muted system render. Added a new
      `FeedItemMessenger` component that handles both channels and wired
      it into `FeedItemSwitch`. This is why the audit saw "empty feeds"
      on most leads — Telegram messages WERE in the DB but didn't render.
- [x] Inbox thread grouping — added a `normalizeSubject` helper that
      strips Re:/Fwd:/Пересл:/Отв: prefixes, and the page renders
      follow-up rows in the same thread with reduced contrast + indent
      and a «↳ продолжение треда» badge. No backend changes — pure
      visual signal so the audit's «один тред × 3 одинаковые карточки»
      complaint goes away. Full thread grouping needs `thread_id` on
      `InboxItem` (Gmail API has it) — tracked as a follow-up.

### G4 — Today inline actions

- [x] Inline checkbox on each /today task row — restructured the row so
      the checkbox button lives outside the row Link (so clicking it
      doesn't navigate). Uses the existing `useCompletePlanItem` mutation
      (`POST /daily-plans/items/{id}/complete`) instead of forcing the
      manager into the lead card.
- [x] Day progress bar in the TaskListWidget header — «X/Y» pill +
      thin orange bar, fed by `items.filter(t => t.done).length /
      items.length`. Hidden when there are no items.

### G5 — Mobile pipeline navigation

- [x] Sticky horizontal scrollable chip-bar of stages at the top of the
      mobile `PipelineList` view. «Все» shows every section (prior
      behaviour); selecting a stage collapses the list to that stage
      only. Each chip carries the stage colour dot + lead count. Empty
      filtered state has a «Показать все этапы» reset link.

---

## Pre-PR gates per checkbox

Per `CLAUDE.md`:

- Frontend: `npm run typecheck` + `npm run lint` + `pnpm build` (Next.js 15
  build-time checks fire only during `next build`; `tsc --noEmit` is not enough).
- Backend (G3 auto-link, possibly G4): `python -m py_compile` on touched
  modules, `pytest --collect-only`, then targeted tests.

Commit messages reference the gate, e.g. `feat(knowledge): G1 — roadmap placeholder`.

---

## Linked sources

- v0 audit (production): `~/Downloads/crm-ui-ux-analysis (4)/components/audit-production.tsx`
- v0 screenshots: `~/Downloads/crm-ui-ux-analysis (4)/screenshots/` (18 PNGs)
- v0 mockups (visual references, NOT specs):
  `~/Downloads/crm-ui-ux-analysis (4)/components/mockup-*.tsx`
