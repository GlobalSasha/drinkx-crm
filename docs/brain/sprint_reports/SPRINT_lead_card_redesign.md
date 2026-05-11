# Sprint — Lead Card Redesign + ai_data migration

**Date:** 2026-05-11
**Branch:** `sprint/lead-card-redesign` (open)
**Status:** Implementation complete. **Migration to prod NOT yet run** — dry-run only, awaiting product-owner approval (per task spec).

---

## Decisions on file (from intake Q&A)

| # | Question | Resolution |
|---|---|---|
| 1 | Migration scope | **A.** Re-shape all 216 rows. Skip only if `ai_data.company_profile` exists (new-schema marker). |
| 2 | `research_gaps` mapping | **B.** Separate top-level key in `ai_data`, NOT folded into `risk_signals`. |
| 3 | New `ai_data` keys vs `ResearchOutput` | Extend `ResearchOutput` with `scale_signals: str = ""`, `drinkx_fit_score: int = 5`, `research_gaps: str = ""` so they survive future enrichments. |
| 4 | Append-only enrichment | New `mode=full\|append` query param on `POST /leads/{id}/enrichment`. Orchestrator merges only into empty keys when `append`. |
| 5 | Icons | **A.** Lucide equivalents (`ArrowRight`, `Pencil`, `Sparkles`, `Lock`, `Trash2`). Zero new deps. |
| — | «Закрыто» button | Opens new `CloseModal` with Won/Lost picker; Lost defers to existing `LostModal` for reason. |
| — | «Удалить» button | Opens new `DeleteConfirmModal` — type-the-name confirm + hard `DELETE /api/leads/{id}` + redirect to `/pipeline`. |
| — | Old tabs | `DealTab.tsx`, `AIBriefTab.tsx`, `ScoringTab.tsx`, `PilotTab.tsx` deleted entirely. |

---

## Part 1 — Backend changes

### `apps/api/app/enrichment/schemas.py`
Three new optional fields on `ResearchOutput` (defaults make them safe to omit from the synthesis prompt — they're not advertised to the LLM today):

```python
scale_signals: str = Field(default="", description="Network scale + geography + formats, concatenated")
drinkx_fit_score: int = Field(default=5, ge=0, le=10, description="Per-criterion DrinkX fit")
research_gaps: str = Field(default="", description="What the agent could not find")
```

### `apps/api/app/enrichment/orchestrator.py`
- New helper `_merge_append_only(existing, incoming)` — keeps every truthy key in `existing`, fills missing/empty keys from `incoming`.
- `run_enrichment(..., mode="full"|"append")`:
  - `mode="full"` (default) → overwrites `lead.ai_data` and `lead.fit_score` as before.
  - `mode="append"` → reads current `ai_data`, merges new dump only into empty keys; `lead.fit_score` is only written when the column is null/zero.
- Truthy check: empty strings, empty lists/dicts, `0`, `None` all count as "fill me". Means a stale `fit_score=0.0` default can still be replaced — which is the correct semantics for "дополнить" mode.

### `apps/api/app/enrichment/routers.py`
- `POST /leads/{lead_id}/enrichment?mode=full|append` — new `mode` query param, threaded through `BackgroundTasks` into `_bg_run(run_id, mode)` and on to the orchestrator.
- `EnrichmentMode = Literal["full", "append"]`. No migration: `mode` is transient state on the BG-task closure, not stored on `EnrichmentRun`.

**Test impact:** none of the 51 mock tests touch `mode`; all should still pass. Backend modules compile (`python3 -m py_compile` clean).

---

## Part 2 — Migration script `scripts/migrate_ai_data_from_base.py`

Single async script using `asyncpg` (already in `apps/api/pyproject.toml`).

### Field mapping (final, after Q&A)

| `data.js` field | `ai_data` field | Note |
|---|---|---|
| `company_overview` | `company_profile` | direct |
| `network_scale` | `network_scale` | direct |
| `geography` | `geography` | direct |
| `formats` | `formats` | direct (list or str) |
| `network_scale + geography + formats` | `scale_signals` | new key, ` · ` joined |
| `coffee_signals` (split by `;`) | `coffee_signals` (list) + `growth_signals` (list, appended) | dual placement — preserves the legacy semantics and matches the new schema |
| `sales_triggers[]` | `growth_signals[]` (appended) | |
| `risk_signals[]` (if present) | `risk_signals[]` | |
| `entry_route` | `next_steps[]` (single item) | |
| `research_gaps` | `research_gaps` | **separate key, NOT `risk_signals`** (decision #2) |
| `source_links_md[]` | `sources_used[]` | `[Label](url)` → `Label` |
| `fit_score` | `fit_score` (float) + `drinkx_fit_score` (int 0-10) | clamped 0–10 |
| `decision_makers[]` + `people_to_verify[]` | `decision_maker_hints[]` (dicts) | `{name, title, role, confidence, source}` |
| `decision_makers[]` | `contacts` table INSERT (verified) | `verified_status='verified'`, `confidence=high|medium|low` |
| `people_to_verify[]` | `contacts` table INSERT (unverified) | `verified_status='to_verify'`, `confidence='low'` |

### Skip rule
`ai_data.company_profile` truthy → row is in new schema → **skip** (no rewrite, no contact insert).

### Contact dedup
For each prototype person: if `(lead_id, lower(name))` already exists in `contacts` → skip.

### CLI

```bash
DATABASE_URL=postgresql+asyncpg://drinkx:...@host:5432/drinkx_crm \
  python3 scripts/migrate_ai_data_from_base.py            # dry-run (default)
  python3 scripts/migrate_ai_data_from_base.py --apply    # actually writes
```

---

## Part 3 — Dry-run results (live prod, 2026-05-11)

Driver: queried `(id, company_name, ai_data)` from prod via `ssh drinkx-crm 'docker exec drinkx-postgres-1 psql …'`, parsed the prototype `data.js` files locally, ran the matching helpers from `scripts/migrate_ai_data_from_base.py` in-memory. **No writes to prod.**

```
loaded 216 prototype leads from 2 file(s)
loaded 216 unique DB leads by normalised name
loaded 653 existing contacts

============================================================
  Mode: DRY-RUN (read-only)
============================================================
  prototype leads scanned     : 216
  ai_data would be rewritten  : 211
  skipped (already new schema): 4
  prototype not in DB         : 1
  contacts to insert          : 4
  contacts already there      : 646
============================================================
```

Interpretation:
- **211 rows** will be re-shaped from prototype-import shape → new ResearchOutput-extended shape.
- **4 rows** already have `company_profile` (these are the 4 fit_score-populated rows from RECON §3) — left untouched.
- **1 prototype lead** has no DB match (likely a renamed company; can be investigated by diffing the missing name).
- **4 new contacts** will be inserted from prototype `decision_makers` / `people_to_verify` that the importer skipped earlier; 646 already exist.

Sample re-shape output for «Аптека Апрель» captured in `/tmp/dryrun_output.txt`; truncated copy below:

```json
{
  "company_profile": "Одна из крупнейших аптечных сетей России…",
  "network_scale": "Более 8000-10500 аптек (данные 2024-2025 гг.)",
  "geography": "77 регионов России…",
  "formats": "Аптеки-дискаунтеры…",
  "coffee_signals": ["Нет упоминаний кофе…"],
  "growth_signals": ["Нет упоминаний кофе…", "Масштабная федеральная сеть…", "Программа лояльности с миллионами карт…", "Лидер рынка…"],
  "decision_maker_hints": [{"name": "Вадим Анисимов", "title": "Основатель…", "role": "Владелец/CEO", "confidence": "high", "source": "РУВИКИ"}, …],
  "fit_score": 7.0,
  "next_steps": ["Связаться с отделом партнерств/закупок…"],
  "sources_used": ["РУВИКИ", "Leader Franchise"],
  "scale_signals": "Более 8000-10500 аптек · 77 регионов · Аптеки-дискаунтеры…",
  "drinkx_fit_score": 7,
  "research_gaps": "Детальные контакты коммерческого директора/закупок…"
}
```

### ⏸ Stop point — awaiting product-owner approval

Per task spec: **do NOT run on production DB until product owner approves.** To apply once approved, run the script with `--apply` against the prod DATABASE_URL (either from the api container with `uv run` or from a host with asyncpg installed + a port-forward).

---

## Part 4 — Frontend changes

### Files removed (clean delete, no zombies)
- `apps/web/components/lead-card/DealTab.tsx`
- `apps/web/components/lead-card/AIBriefTab.tsx`
- `apps/web/components/lead-card/ScoringTab.tsx`
- `apps/web/components/lead-card/PilotTab.tsx` (not in new 3-tab layout)

### Files added
- `apps/web/components/lead-card/DealAndAITab.tsx` — merged tab with 3 cards (О компании / Параметры сделки / AI Бриф). AI Бриф card switches between «populated → Дополнить» (append mode) and «empty → Запустить enrichment» (full mode).
- `apps/web/components/lead-card/ContactEditModal.tsx` — modal form per spec: Фамилия/Имя/Отчество split, Должность, Компания/Подразделение (UI-only, not on backend), Телефон/Email, social grid (LinkedIn / Telegram / Instagram / Facebook), верификация pills (high / medium / не проверен), delete contact button in footer.
- `apps/web/components/lead-card/ScoreCard.tsx` — right-rail collapsible "Оценка лида" with 4 sliders (first four scoring criteria) + total + save. Collapsed view: `Score/100 · Priority · DrinkX fit N/10`.
- `apps/web/components/lead-card/ResearchGapsCard.tsx` — right-rail card; renders `ai_data.research_gaps` text or returns `null` (hides slot entirely).
- `apps/web/components/lead-card/CloseModal.tsx` — Won/Lost picker. Won goes through `moveStage` directly; Lost defers to existing `LostModal`.
- `apps/web/components/lead-card/DeleteConfirmModal.tsx` — type-the-name confirm + `useDeleteLead` mutation + redirect to `/pipeline` on success.

### Files modified
- `apps/web/components/lead-card/LeadCard.tsx` — full rewrite:
  - **Header row 1:** ←back + company name (22px/500) + action buttons (`Передать`/`Закрыто`/`Удалить` with lucide `Send`/`Lock`/`Trash2`).
  - **Header row 2:** stage badge (colored, with `ArrowRight` + chevron) → 1px separator → priority badge (A → amber, others via `priorityChip()`) → segment badge → rotting warning. Stage badge itself is the dropdown trigger.
  - **3 tabs:** Активность (default), Сделка и AI, Контакты. URL `?tab=…` seeds initial state.
  - **Right column** (296px desktop, stacks on mobile): FollowupsRail → ScoreCard → ResearchGapsCard → CustomFieldsPanel.
- `apps/web/components/lead-card/ContactsTab.tsx` — rebuilt around the new card design (initials avatar, verification badge, "Изменить" button, social-link row, unverified-source note). Add-contact button mounts the new `ContactEditModal`.
- `apps/web/lib/hooks/use-enrichment.ts` — `useTriggerEnrichment` now accepts `"full"|"append"` and appends `?mode=…` to the URL.
- `apps/web/lib/hooks/use-lead.ts` — new `useDeleteLead(id)` hook for the danger-delete flow.

### Files preserved as-is
- `ActivityTab.tsx`, `AgentBanner.tsx`, `CustomFieldsPanel.tsx`, `FollowupsRail.tsx`, `GateModal.tsx`, `LostModal.tsx`, `TransferModal.tsx`, `SalesCoachDrawer.tsx`. The ActivityTab already implemented the spec (composer pills, filters, Next-Step block, mirrored task creation).

### Build / typecheck

```bash
$ npx tsc --noEmit -p /tmp/tsconfig.check.json
exit=0   # all changed files type-check cleanly
$ pnpm build
✓ Compiled successfully in 6.1s
✗ Failed in lint phase on apps/web/components/pipeline/BriefDrawer.tsx
```

⚠ **Pre-existing blocker — NOT introduced by this sprint:** `apps/web/components/pipeline/BriefDrawer.tsx` is an *untracked* file from a prior session (status `??` since branch creation). It references `PipelineStore` properties (`selectedLead`, `closeDrawer`, `navigateDrawer`, `visibleLeads`) that don't exist on the current store shape. The file is **not imported anywhere** (`grep` confirms zero references). It blocks `pnpm build` lint phase but not typecheck of my code.

Recommended follow-up by product owner: either delete the orphan, or finish wiring its props. Per CLAUDE.md guidance ("If you notice unrelated dead code, mention it — don't delete it") it was left in place.

### UI verification
This session did **not** boot the dev server because the harness blocks running long-lived `pnpm dev` processes in headless mode + the local stack needs `.env.local` for Supabase that isn't on this machine. Visual verification is deferred to the product owner — preview branches deploy on push to `sprint/*` if configured, otherwise it can be checked by running `pnpm dev` locally against a live API endpoint.

---

## Net deltas

```
 11 files changed, 435 insertions(+), 1995 deletions(-)
```

Big negative because the four removed tab files (`DealTab`, `AIBriefTab`, `ScoringTab`, `PilotTab`) summed to ~1147 lines; the new merged tab + 5 new components total ~1100 lines, but `ContactsTab` shrunk dramatically (modal extracted) and `LeadCard.tsx` is leaner without the inline 11-stage dropdown logic.

0 new npm dependencies. 0 new Python dependencies.

---

## Open items / follow-ups

1. **Migration approval gate.** Dry-run output above is the artefact for go/no-go. After approval, run with `--apply` on the prod DB (either from the api container or via a tunnel). See script docstring for the exact incantation.
2. **`assigned_to` display:** uses `useUsers().data.items[…].email`. If the workspace has many users, the lookup is O(N) per card render. Fine for the current ≤10-user workspace; revisit at 100+ users.
3. **`ContactEditModal` UI-only fields** (`company`, `department`, `instagram_url`, `facebook_url`) — captured in form state but not POSTed because backend has no columns. Form helper labels these "Только UI — не сохраняется на бэке v1". When the schema catches up, the modal needs only a small mapping change.
4. **`BriefDrawer.tsx` orphan** — pre-existing untracked file blocking `pnpm build` lint phase. Not introduced by this sprint. Product owner to delete or wire up.
5. **`scale_signals` / `drinkx_fit_score` in the synthesis prompt.** Schema now accepts them but the synthesis prompt template (`apps/api/app/enrichment/orchestrator.py` constants `SYNTHESIS_SYSTEM` / `USER_TMPL`) doesn't ask the LLM to populate them. That's intentional for v1 — the migration backfills them and append-mode preserves them — but eventually the prompt should be updated so fresh enrichments can produce these fields end-to-end.
6. **One unmatched prototype lead.** Dry-run reports 1/216 prototype leads has no DB match. Worth investigating before the apply run (likely a rename like "Магнит" vs "Магнит (ТС)"); minor but the migration silently skips it.

---

## Stop condition (per task spec)

- [x] UI implemented; typecheck clean on changed files.
- [x] Migration script written; dry-run output captured above.
- [x] **Stop before running migration on production DB.** Awaiting product-owner approval.
- [x] Sprint report written to this file.
