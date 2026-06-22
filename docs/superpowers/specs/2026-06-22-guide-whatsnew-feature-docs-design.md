# Guide: «Что нового» changelog + catch-up feature docs

**Date:** 2026-06-22
**Type:** Docs / manager-facing content (in-app `/guide`)

## Problem

The in-app manager guide (`apps/web/app/(app)/guide/page.tsx`) was last refreshed
2026-05-24 (PR #97). Since then ~7 manager-visible feature areas shipped and are
**undocumented for managers**: the КП module (PR #135–137), website-leads inbox
(«Входящие заявки», #126/#132), lead deduplication + merge (#105/#109/#110),
team dashboards / manager portfolio (#101/#122), stage-dwell analytics
(«где застревают сделки», #121), and UTM channel attribution (#108/#111).

There is also **no place where managers can see what changed between releases**.
The owner wants an ongoing «Что нового» (release announcements) surface in the
same place managers already read — the guide — listing each version, what
appeared, and how it works.

## Scope

- A new **«Что нового»** section at the TOP of `/guide`: a maintainable,
  versioned changelog managers read. Seeded with the real release history since
  the last guide refresh. Newest first. Each entry links to its detailed section.
- **New detailed sections** in the guide: `quote`, `duplicates`, `incoming`,
  `team`.
- **Extend existing sections**: `forecast` (stage-dwell + channels/UTM analytics),
  `leadcard` (a line on «Найти дубли» and the UTM source on a lead).
- **TOC / GLOSSARY / FAQ** updated for the new content.
- A **maintenance convention** (code comment in `page.tsx` + a short note in
  `docs/brain/`) describing how to add a new «Что нового» entry going forward.

### Out of scope

- The separate developer-facing technical docs (`docs/features/`) — per the
  two-deliverables rule, that is a separate artifact, done later if requested.
- A DB-backed announcements feature (admin posts releases, unread badges) — YAGNI.
- A standalone `/whats-new` route — the owner wants it inside `/guide` («там же»).
- Re-documenting unchanged screens or non-manager-facing work (refactors, CI,
  ops/logging, security hardening).

## Approach

All content is **static** inside the existing `apps/web/app/(app)/guide/page.tsx`,
following the file's established patterns (`TOC` array, data arrays like
`GLOSSARY`/`FAQ`, and the `Section` / `Card` / `Alert` / `Steps` / `KV`
components). No backend, no new route, no new dependency.

Rejected: a separate `/whats-new` route (not «там же»); a DB-backed announcements
domain (new domain + API + UI — overkill for a changelog the owner edits in code).

## Design

### 1. «Что нового» changelog

A new `RELEASES` data array near the other data arrays:

```ts
type ReleaseItem = { feature: string; how: string; anchor?: string };
type Release = { version: string; date: string; title: string; items: ReleaseItem[] };

const RELEASES: Release[] = [ /* newest first */ ];
```

- **Version scheme:** calendar versions `vYYYY.M` (e.g. `v2026.6`) — honest, no
  fake semver, trivially bumpable. Shown as a small chip next to the date.
- Rendered as a new `<Section id="whatsnew" title="Что нового">` placed FIRST in
  the body (right after the hero, before `start`), and as the FIRST `TOC` entry
  (icon: `Sparkles`). Each release is a `Card` with the version chip + date +
  title, then its items as a list of «**что появилось** → как работает», each
  item optionally linking to its detailed section via `#anchor`.

**Seed entries (newest first), grounded in real releases:**

1. `v2026.6` · 22 июня · **Коммерческие предложения (КП)** → `#quote`
   - Каталог товаров в Настройках; сборка КП в карточке лида; печать/PDF;
     «Сумма сделки = итог».
2. `v2026.6` · июнь · **Заявки с сайта** → `#incoming`
   - Лента «Входящие заявки»; контакты подтягиваются из формы; авто-ответ
     настраивается под каждую форму.
3. `v2026.6` · июнь · **Качество данных** → `#duplicates`
   - «Найти дубли» и склейка в карточке; UTM-источник на лиде; нормализация
     телефонов.
4. `v2026.6` · июнь · **Аналитика** → `#forecast`, `#team`
   - «Где застревают сделки» в Прогнозе; командные дашборды и портфель менеджера.

### 2. New detailed sections

Each is a `<Section>` using `Steps` / `Card` / `Alert` / `KV`, plain Russian,
aimed at a non-technical manager. Bullet-level content (exact UI labels verified
against the components during implementation):

- **`quote` — «Коммерческие предложения (КП)»**
  - Где: вкладка «КП» в карточке лида; каталог — Настройки → «Каталог КП».
  - Шаги: «Новый КП» → добавить позиции (из каталога или вручную) → скидки по
    строке и на КП, ставка НДС (20/0/своя) → итоги считаются автоматически.
  - Статусы: черновик → отправлено → принято/отклонено; черновик можно удалить.
  - Печать: «Печать / PDF» открывает чистый лист → Ctrl/⌘+P → сохранить PDF.
  - «Сумма сделки = итог» переносит итог КП в сумму сделки.
  - Alert: КП из CRM не отправляются — менеджер сам шлёт сохранённый PDF.
- **`duplicates` — «Дубли и склейка лидов»**
  - Где: карточка лида → меню «⋯» → «Найти дубли».
  - Как идёт склейка; что «лид поглотил дубликаты» означает; данные не теряются.
- **`incoming` — «Входящие заявки с сайта»**
  - Где: пункт меню «Входящие заявки» (`/incoming`).
  - Что показывает: заявки с форм на сайтах; контакт из заявки; авто-ответ.
- **`team` — «Командные дашборды»**
  - Где: «Команда» (`/team`); кому видно (руководитель/менеджер).
  - Дашборд руководителя; портфель сделок менеджера по этапам.

### 3. Extend existing sections

- **`forecast`** — добавить карточку «Где застревают сделки» (аналитика времени
  на этапе) и упоминание разреза по каналам/UTM.
- **`leadcard`** — одна строка про «Найти дубли» (меню «⋯») и про UTM-источник,
  который виден в карточке.

### 4. TOC / GLOSSARY / FAQ

- **TOC:** prepend `whatsnew`; add `quote`, `incoming`, `duplicates`, `team` in
  sensible positions; keep icons from `lucide-react` (no new dep).
- **GLOSSARY:** add «КП», «Дубль», «Входящая заявка», «UTM-источник».
- **FAQ:** add 3–4 entries — как собрать КП и сохранить PDF; где заявки с сайта;
  как объединить дубли; где смотреть, на каком этапе застревают сделки.

### 5. Maintenance convention

- A comment block above `RELEASES` in `page.tsx`: how to add a new entry (prepend
  to `RELEASES`, bump `vYYYY.M`, add/refresh the detailed `Section`, add a TOC
  entry if it's a new screen).
- A short note in `docs/brain/` (e.g. append to `06_OPERATING_PROTOCOL.md` or a
  one-liner in `00_CURRENT_STATE.md`) pointing future sessions to keep «Что
  нового» updated when shipping manager-visible features.

## Testing / checks

- `npm run typecheck` — must pass.
- `npm run lint` — 0 problems (watch the `drinkx/no-arbitrary-px` rule; reuse
  existing spacing tokens).
- `pnpm build` from `apps/web` — `/guide` compiles (it's a static page; no routing
  changes, but build is the project's hard gate).
- Manual: anchors resolve (TOC → section), «Что нового» renders newest-first,
  links from release items jump to the right section.

## Migration & deploy notes

- Single-file content change (plus a small `docs/brain/` note). No migration, no
  dependency, no API. Ships via the normal `main`→deploy pipeline.
- Accuracy gate: verify each asserted UI label against the live component while
  writing (the 2026-05-24 refresh hit several «discrepancies with reality»; avoid
  repeating that — read the component, don't assume).
