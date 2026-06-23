# Lead card v3 — two-pane layout + «next step» prompt

**Date:** 2026-06-23
**Type:** Feature / UX redesign (`apps/web/components/lead-card/*`)

## Problem

The lead card is tab-centric: header + stage stepper + **7 tabs** (Активность,
Информация, Контакты, КП, Задачи, Заметки, Архив). The essentials a manager needs
at a glance — deal amount, priority, primary contact, the next planned step — live
inside the «Информация»/«Контакты»/«Задачи» tabs, so the manager hunts through tabs
to see the state of a deal. Two specific gaps vs. the owner's reference (Bitrix24):

1. **No always-visible info.** Bitrix shows key info in a left column and activity
   on the right, both at once. Ours hides it behind tabs.
2. **No «plan the next step» nudge.** Bitrix prompts «Создайте дело — запланируйте
   следующий шаг» when you leave a card with no scheduled activity.

Also, the AI assistant (Блейк) in the card — the `@Блейк` composer mode and the AI
brief — currently adds confusion rather than value and should leave the card flow.

## Scope

Shipped in two phases:

- **Phase 1 — two-pane layout (no Блейк in the card).** The committed deliverable.
- **Phase 2 — «next step» prompt on leaving the card.**

### In scope

- Restructure `LeadCard` from tab-centric to **two-pane**: a left info column that
  is always visible + a right column whose content switches via tabs.
- Left column (always visible): summary → next step → deal params → primary contact
  → source → custom fields.
- Right column: a composer at the top + the active tab's content (Активность default).
- Remove the **«Информация»** tab — its content (deal params, source) moves to the
  left column.
- **Remove Блейк from the card:** drop the `@Блейк` composer routing/hint and the
  AI brief block. (Блейк stays everywhere else — /guide, the product at large; the
  feed still renders any historical AI items.)
- **Phase 2:** on leaving the card, if the lead has **no open future task**, show a
  modal to schedule one (text + date, default tomorrow 18:00) → «Сохранить» creates
  a task / «Пропустить» dismisses.

### Out of scope

- Removing Блейк from the rest of the product.
- Any backend change — the redesign uses existing hooks/endpoints only
  (`useLead`, `useContacts`, `useLeadTasks`, `useFeed`, deal-field mutations,
  `useLeadQuotes`).
- Changing the task model (tasks stay manager-entered, no AI — see existing
  convention).
- Merging the Задачи/Архив tabs or moving Заметки into the feed (possible later
  cleanup, not now).

## Design

### Frame (full width)

- **Header** (sticky): company name (inline-editable) · stage chip · quick actions
  (call / mail / telegram) · «Закрыть сделку ▾» (Won/Lost) · «⋯» (transfer, find
  duplicates, delete). Unchanged from today (`LeadCardHeader`).
- **Stage stepper** + «N дней на этапе» under the header (`StagesStepper`), unchanged.

### Body — two columns

Desktop (`md:` and up): a CSS grid `[320px] [1fr]`. The left column is `sticky`
near the top so it stays visible while the right column scrolls. Mobile: single
column, stacked — left column first (collapsed-friendly), then the right column.
Mobile-first is preserved.

The left column is **independent of the right-column tab** — switching to КП or
Заметки on the right does not change the left info.

### Left column — content and order (act-now → details)

1. **Сводка** — priority badge, segment, **deal amount** (large). Stage/days already
   live in the header/stepper; the summary leads with money + priority.
2. **Следующий шаг** — the nearest open task for the lead (`useLeadTasks`: filter
   `!task_done`, soonest `task_due_at`): title + due date, click opens the Задачи
   tab. If there is none → a «Запланировать» button that focuses the task composer.
   (This same "has an open task?" check drives the Phase 2 prompt.)
3. **Параметры сделки** — `LeadInfoBlock` (existing inline edit): Сумма, Количество,
   Оборудование, Тип, Приоритет, Сегмент, Город, ИНН, Сайт, Email, Телефон — **with
   the AI brief block removed**.
4. **Основной контакт (ЛПР)** — from `useContacts`, the lead's `primary_contact_id`:
   avatar + name + role + call/email/telegram + «ещё N контактов» → Контакты tab.
5. **Источник / UTM** — `SourceSection`, only for form-sourced leads.
6. **Доп. поля** — `CustomFieldsPanel`, only when the workspace has custom fields.

### Right column — work surface

- **Composer at the top** (moved from the bottom of the feed). Modes: **Дело/Задача ·
  Комментарий** (call/file modes kept). The `@Блейк` prefix detection and the
  «…или @Блейк» placeholder hint are removed.
- **Tab switcher**, then the active tab's content. Tabs (all now secondary detail
  views — the essentials are in the left column):
  - **Активность** (default) — `UnifiedFeed`.
  - **Задачи** — full task list (`TasksTab`).
  - **Контакты** — full contact list (`ContactsTab`).
  - **КП** — `QuoteTab`.
  - **Заметки** — `NotesTab`.
  - **Архив** — `ArchiveTab`.

The «Информация» tab is gone (folded into the left column). Tab count is similar,
but the *essentials* no longer require tab-switching — that is the win.

### Blake removal — exact touch points

- `feed/FeedComposer.tsx`: remove the `@Блейк`-at-start detection branch and the
  AI route; drop «…или @Блейк» from the placeholder. Keep `comment/task/call/file`.
- `LeadInfoBlock.tsx`: remove the collapsible AI brief section.
- `feed/UnifiedFeed.tsx` + `feed/FeedItemAI.tsx`: historical AI feed items still
  render (no new ones are produced); no removal needed there.

### Phase 2 — «next step» prompt on leaving the card

- **Trigger:** the manager tries to leave the lead card (browser back/forward via
  `popstate`, or an in-app navigation initiated from the card) AND the lead has no
  open task (`useLeadTasks` → none with `!task_done`). A navigation guard on the
  lead page intercepts the attempt and shows the modal before completing it.
- **Modal:** «Запланируйте следующий шаг по {company}» — task text input + date
  (default tomorrow 18:00) + «Сохранить» (creates a task via the existing task
  create mutation) / «Пропустить» (proceeds without creating). After either, the
  navigation completes.
- **Risk:** App Router has no built-in `routeChangeStart`. The guard combines a
  `popstate` listener for back/forward with intercepting the card's own exit
  affordances; finalized during Phase 2 implementation. Phase 1 does not depend on it.

## Components / files

- `LeadCard.tsx` — restructure to header + stepper + two-pane grid (left column +
  right column with composer-on-top and tab switcher). This file is already large;
  extract the left column into its own component to keep it focused.
- New `components/lead-card/LeadSummaryPane.tsx` (or `LeftColumn.tsx`) — composes
  summary + next-step + `LeadInfoBlock` + primary-contact + `SourceSection` +
  `CustomFieldsPanel`.
- New `components/lead-card/NextStepCard.tsx` — the «Следующий шаг» block (nearest
  open task / «Запланировать»).
- New `components/lead-card/PrimaryContactCard.tsx` — primary-contact summary for
  the left column (reads `useContacts`).
- `LeadInfoBlock.tsx` — drop the AI brief.
- `feed/FeedComposer.tsx` — drop `@Блейк`; `feed/UnifiedFeed.tsx` — composer to top.
- `DealAndAITab.tsx` — removed (its pieces move to the left column).
- **Phase 2:** new `components/lead-card/NextStepPrompt.tsx` + a navigation-guard hook.

## Testing / checks

- `npm run typecheck` · `npm run lint` (0 problems; watch `drinkx/no-arbitrary-px`)
- `pnpm build` — **mandatory** (routing + Suspense around `useSearchParams`; the tab
  state currently reads `?tab=`).
- Manual: a lead with tasks and without; mobile single-column; switching right-column
  tabs leaves the left column intact; inline edit of deal params still works.
- Apply the `make-interfaces-feel-better` skill during implementation for polish
  (hover/focus states, optical alignment, spacing rhythm).

## Notes

- Keep the existing design system (brand tokens, Manrope, spacing scale 4-8-12-16-24-32,
  no new fonts). This is an IA/layout change, not a restyle.
- The card preserves `?tab=` deep-linking for the right-column tabs.
