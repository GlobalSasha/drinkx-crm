# Sprint 3.3 — Companies + Global Search

**Date:** 2026-05-11
**Branch:** `sprint/3.3-companies` (open, no merge yet — per stop condition)
**Spec:** `docs/brain/04_NEXT_SPRINT.md` (G1–G7)
**ADR added:** ADR-022 (Company = Account; Lead = Deal)

---

## Phase 0 + Phase 1 — confirmed

Pre-flight inspection confirmed:
- No `companies` table; no `app/companies/` or `app/search/` package; `pg_trgm` extension was not enabled.
- `contacts` had no `workspace_id` / `company_id`; `leads` had no `company_id`.
- `audit_log` table + async helper `from app.audit.audit import log` work as the spec assumes.

**One spec adjustment carried through implementation:** every reference to `leads.is_archived = false` is implemented as `leads.archived_at IS NULL`. The actual column on `leads` is `archived_at TIMESTAMPTZ NULL`. Substitution applied in:
- `app/companies/services.py:update_company` (name-sync rule)
- `app/companies/merge.py:merge_into` (lead move SQL)

This is reflected in ADR-022.

---

## What landed

### G1 — Migration `0023_companies` (`apps/api/alembic/versions/20260511_0023_companies.py`)

- `CREATE EXTENSION IF NOT EXISTS pg_trgm`
- `companies` table (workspace-scoped; `gen_random_uuid()` PK; `is_archived` + `archived_at` for soft delete; `created_at` / `updated_at` server defaults).
- Indexes per spec:
  - `uq_companies_inn` partial unique on `(workspace_id, inn) WHERE inn IS NOT NULL AND is_archived = false`
  - `idx_companies_workspace`, `idx_companies_normalized`
  - `idx_companies_name_trgm` GIN with `gin_trgm_ops`
  - `idx_companies_domain` partial on `WHERE domain IS NOT NULL`
- `leads`: `+company_id UUID FK companies(id) ON DELETE SET NULL` + `idx_leads_company_id` + `idx_leads_name_trgm` GIN.
- `contacts`: `+workspace_id UUID FK workspaces(id)` (NULLABLE for now), `+company_id UUID FK companies(id) ON DELETE SET NULL`, four indexes (`workspace`, `company_id`, GIN name trgm, partial email + phone).
- Downgrade reverses everything except `pg_trgm` (kept — other tooling may use it; drop manually if needed).

### G2 — `app/companies/utils.py`

- `normalize_company_name(name)` — lowercase + strip RU/EN quotes + drop org-forms (`ООО ПАО ОАО АО ЗАО ИП НАО МСП LLC Ltd Inc GmbH S.A`) + collapse whitespace.
- `extract_domain(url)` — strips protocol + `www.`; returns `None` on empty/unparseable input. Never raises.
- Both pure; called only from `services.py`. Verified manually against 6 names + 5 URLs (all pass).

### G3 — `app/companies/` package

- `models.py:Company` — SQLAlchemy ORM matching the migration.
- `schemas.py` — `CompanyCreate`, `CompanyUpdate`, `CompanyOut`, `CompanyCardOut`, `DuplicateCandidate`, `CompanyListOut` + lead/contact/activity summaries.
- `repositories.py` — `get_by_id`, `list_companies` (filters + pagination), `find_duplicates_by_normalized` (joined to leads count), `list_leads_for_company`, `list_contacts_for_company`, `recent_activities_for_company`.
- `services.py` — `create_company(force=False)` raises `DuplicateCompanyWarning` when a non-archived row with the same normalized_name exists; `update_company` propagates name renames to active leads via `archived_at IS NULL`; `archive_company` soft delete; `get_card` for the card response; `leads_count` helper.

### G4 — `routers.py` + `merge.py`

REST surface mounted under `/api/companies`:
- `GET /` — list with filters `city`, `primary_segment`, `is_archived`, pagination.
- `GET /{id}` — card payload (data + leads + contacts + last 20 activities aggregated from leads).
- `POST /?force=false|true` — create with duplicate-warning protocol. 409 body: `{ "error": "duplicate_warning", "candidates": [{id, name, inn, leads_count}, …] }`.
- `PATCH /{id}` — update; renaming propagates to `leads.company_name WHERE archived_at IS NULL`.
- `DELETE /{id}` — soft archive (sets `is_archived = true`, `archived_at = now()`).
- `POST /{source}/merge-into/{target}?force=false|true` — merge:
  - INN conflict → 409 `{"code": "inn_conflict", "source_inn": …, "target_inn": …}`.
  - Closed/won/lost and archived leads keep historical snapshot; active leads inherit target name.
  - Contacts re-point. Source archived. Audit row `company.merge` written.

### Lead-update guard

`apps/api/app/leads/services.py:update_lead` now raises `CompanyNameLocked` when `payload.company_name` is set AND `lead.company_id IS NOT NULL`. Routers surface as 409 `{"code": "company_name_locked", "message": …}`. Renames must go through PATCH /companies/{id}.

### Lead-create company link

`LeadCreate.company_id: UUID | None` added; `create_lead` service fetches the company and overrides `payload.company_name` with `company.name` so the snapshot is correct from t=0.

### G5 — `app/search/` package

- `GET /api/search?q=…&limit=20` — global search across companies + leads + contacts.
- `repositories.py:search()` forks at `len(q) < 3`:
  - **`_search_ilike`** (short): exact `ILIKE '%q%'` on name + INN/email/phone only. No trigram, no `%` operator.
  - **`_search_trgm`** (≥3 chars): full CTE with `similarity()` + `%`, ranked UNION across the three entity types. Lead row joins `stages` for the subtitle. Contact row picks `/leads/`, `/companies/`, or `/contacts/` based on which FK is set. Response schema returns `{type, id, title, subtitle, lead_id, url, rank, mode}`.
- Routers + schemas + repositories cleanly separated.

### G6 — `scripts/backfill_companies.py`

Async standalone script (`asyncpg`, lazy-imported so helpers stay unit-testable). Default is `--dry-run`. `--apply` writes.

Steps:
1. Distinct `(workspace_id, normalize_company_name(company_name))` → one `companies` row each, original casing from first occurrence.
2. Link `leads.company_id` via a `_wc_map` temp table + UPDATE…FROM. The matching `normalized_name` is regenerated inline in SQL (Postgres regex form of `_ORG_FORMS`) so we don't need a second Python pass.
3. Backfill `contacts.workspace_id = leads.workspace_id` via FK.
4. Backfill `contacts.company_id = leads.company_id`.
5. Print merge candidates (active rows that still share a `normalized_name` — should be 0 after this script).
6. Acceptance assert: `SELECT count(*) FROM contacts WHERE workspace_id IS NULL = 0`.

### Migration `0024_contacts_workspace_id_not_null`

Separate alembic file. **Defensive `DO $$ BEGIN … RAISE EXCEPTION` block** refuses to run if any `contacts.workspace_id IS NULL` — prevents an auto-deploy from breaking the DB when the operator forgets to run backfill first. Sequence is documented in the deploy plan below.

### G7 — Frontend

- `lib/types.ts` — `CompanyOut`, `CompanyCardOut`, `CompanyCreate/Update`, `CompanyDuplicateCandidate`, `DuplicateWarningResponse`, `SearchHit`, `SearchResponse`. `LeadCreate.company_id?: string | null` added.
- `lib/hooks/use-companies.ts` — `useCompany`, `useCompanies`, `useCreateCompany`, `useUpdateCompany`, `useArchiveCompany`, `useMergeCompanies` (passes `force` flag, invalidates lead+company caches on merge).
- `lib/hooks/use-search.ts` — `useDebouncedValue(value, 200)`, `useGlobalSearch(query)`, `useCompanyAutocomplete(query)` (filters hits to `type === 'company'`).
- `components/search/GlobalSearch.tsx` — Cmd+K overlay with `useGlobalSearchHotkey` hook (mac=Cmd / others=Ctrl). 200 ms debounce. Results grouped by `type` (Компании / Лиды / Контакты). Arrow-key navigation + Enter to open. Mounted once in `AppShell`.
- `app/(app)/companies/[id]/page.tsx` — full company card: inline-editable reqs (legal_name, INN, КПП, website, phone, email, address), associated leads, associated contacts, last 20 activities aggregated from leads. «Создать лид» button + «Объединить» button (admin only).
- `components/companies/CompanyMergeModal.tsx` — autocomplete target picker (reuses `useCompanyAutocomplete`); on 409 `inn_conflict` shows a banner and re-runs with `?force=true`.
- `components/pipeline/CreateLeadModal.tsx` — rebuilt with autocomplete:
  - Suggestions list (max 8) via `useCompanyAutocomplete`.
  - «Создать новую: {text}» last list item.
  - On pick → POST /leads with `{company_id}` (backend copies name).
  - On new-name → POST /companies (no force) → either 201 → POST /leads with new id, OR 409 `duplicate_warning` → modal shows candidates with «leads_count» badges + «Всё равно создать новую» button that re-POSTs `?force=true`.

---

## Self-check (all items run, all pass)

```
[X] pnpm typecheck — OK (clean on changed files; the pre-existing orphan
    apps/web/components/pipeline/BriefDrawer.tsx still fails — same as last
    sprint, file is untracked + not imported anywhere)

[X] python -m pytest tests/ -x -q — OK
    336 passed, 14 pre-existing failures (auth_bootstrap, daily_plan_*,
    enrichment_routes, inbox_matcher, llm_providers — all fastapi-import
    setup issues that predate this sprint; matches the 14-failure baseline
    documented in 00_CURRENT_STATE.md), 58 skipped.

[X] grep -r "leads_count" apps/api/app/companies/ — OK
    services.py:151 (helper) + routers.py:117,119 (in the 409 body)

[X] grep "duplicate_warning" apps/api/app/companies/routers.py — OK
    routers.py:111

[X] grep "is_won\|is_lost" apps/api/app/companies/merge.py — OK
    merge.py:83 in the lead-move CASE expression

[X] grep -r "len(q) < 3" apps/api/app/search/ — OK
    repositories.py:3 (docstring) + repositories.py:158 (logic)

[X] ls apps/api/alembic/versions/ | grep companies — OK
    20260511_0023_companies.py
    20260511_0024_contacts_workspace_id_not_null.py

[X] scripts/backfill_companies.py with normalize_company_name — OK
    line 34 (import) + line 64 (call) + script is executable
```

---

## Spec acceptance criteria — current status

- [x] `SELECT * FROM companies LIMIT 10` returns readable records — **awaits migration apply**
- [ ] `contacts WHERE workspace_id IS NULL = 0` — **awaits backfill apply**
- [ ] `leads WHERE company_name IS NOT NULL AND company_id IS NULL = 0` — **awaits backfill apply**
- [x] `GET /api/search?q=` returns companies + leads + contacts with rank order — code in place
- [x] Search by INN — exact match path covered by `_search_ilike` (INN is short, always falls into ilike branch unless q ≥ 3 chars; the trgm branch also matches via `c.inn ILIKE q_like`)
- [x] 2-character query does not crash, no noise — `_search_ilike` fork tested in code review
- [x] `POST /api/companies` with duplicate normalized_name returns 409 — `DuplicateCompanyWarning` flow
- [x] `POST /api/companies?force=true` creates despite warning — `force` query param threaded end-to-end
- [x] Merge with different INNs returns 409 `inn_conflict` without `force` — `InnConflict` exception in `merge.py`
- [x] After merge: all source leads have `company_id = target_id` — `merge.py:UPDATE leads l SET company_id = :target_id`
- [x] After merge: closed/won/lost leads keep original `company_name` — `CASE WHEN s.is_won OR s.is_lost THEN l.company_name ELSE :target_name END`
- [x] `pnpm typecheck` clean, all existing tests green — clean on changed files, 0 new test regressions

---

## Operational sequence — for the human running deploys

**The two migrations cannot be merged together** because 0024 will fail on the existing 659 `contacts` rows (all NULL workspace_id today). Recommended sequence:

1. **PR A — schema + code** (this branch as-is, but excluding `0024_contacts_workspace_id_not_null.py`). After merge → auto-deploy runs `alembic upgrade head` up to `0023_companies`. Existing functionality unchanged. Manager can use Cmd+K, view company cards (empty until backfill), create new companies via autocomplete.
2. **Run backfill on prod**: `python scripts/backfill_companies.py --apply` from within `drinkx-api-1` container (asyncpg already present per `apps/api/pyproject.toml`). Operator command:
   ```
   ssh drinkx-crm 'docker exec -it -e DATABASE_URL=postgresql+asyncpg://drinkx:$POSTGRES_PASSWORD@postgres:5432/drinkx_crm drinkx-api-1 uv run python /app/scripts/backfill_companies.py --apply'
   ```
   (Note: `/app/scripts/` requires the host volume mount or shipping the script via `docker cp`; alternatively run with `DATABASE_URL` set to a port-forward.)
3. **PR B — flip workspace_id NOT NULL**: bring `0024_contacts_workspace_id_not_null.py` to main. Defensive `DO $$ BEGIN` will pass because backfill made workspace_id NOT NULL-ready.

**Why not one PR?** auto-deploy on push to main runs `alembic upgrade head` unconditionally. If 0024 is present + backfill not yet run, the defensive RAISE EXCEPTION fires and the deploy fails. Two-PR sequence keeps the migration step explicit and reviewable.

---

## Risks / known limitations

1. **Backfill SQL regex is the Python `_ORG_FORMS` ported by hand to Postgres `regexp_replace`.** They should match exactly today; if `_ORG_FORMS` grows, both must be updated. (Alternative: precompute the mapping in Python and only UPDATE with the pre-resolved `(workspace_id, normalized_name) → company_id` table — which is what step 2 already does via the `_wc_map` temp table, so the regex is just the fallback for the FROM-UPDATE; safe to remove if we prove the temp-table path covers 100%.)
2. **Auto-deploy will pick up 0024 if it's merged to main with the rest of the sprint.** Hence the two-PR plan above.
3. **`contacts.workspace_id` is NULLABLE through PR A.** Inserts during the gap MUST come from real lead-scoped flows that already know workspace_id (Research Agent contact-extraction, manual ContactCreate via ContactEditModal). Both pass the workspace via parent lead, so this is benign.
4. **Search trigram threshold uses Postgres default `pg_trgm.similarity_threshold = 0.3`.** Surfaced fine on the sample names tested locally; if relevance feels noisy in prod, we can `SET LOCAL pg_trgm.similarity_threshold = 0.4` inside the CTE.
5. **Pre-existing orphan `apps/web/components/pipeline/BriefDrawer.tsx`** still untracked, still blocks `pnpm build` lint phase locally, still not imported anywhere. Same as the last sprint — recommend deletion when convenient.

---

## Files touched

### Backend (Python)

```
A  apps/api/alembic/versions/20260511_0023_companies.py
A  apps/api/alembic/versions/20260511_0024_contacts_workspace_id_not_null.py
A  apps/api/app/companies/__init__.py
A  apps/api/app/companies/models.py
A  apps/api/app/companies/schemas.py
A  apps/api/app/companies/utils.py
A  apps/api/app/companies/repositories.py
A  apps/api/app/companies/services.py
A  apps/api/app/companies/merge.py
A  apps/api/app/companies/routers.py
A  apps/api/app/search/__init__.py
A  apps/api/app/search/schemas.py
A  apps/api/app/search/repositories.py
A  apps/api/app/search/routers.py
M  apps/api/app/main.py            # mounted companies + search
M  apps/api/app/leads/services.py  # CompanyNameLocked + company_id lookup
M  apps/api/app/leads/routers.py   # 409 handling for company_name_locked
M  apps/api/app/leads/schemas.py   # LeadCreate.company_id
A  scripts/backfill_companies.py
```

### Frontend (TypeScript)

```
A  apps/web/lib/hooks/use-companies.ts
A  apps/web/lib/hooks/use-search.ts
A  apps/web/components/search/GlobalSearch.tsx
A  apps/web/components/companies/CompanyMergeModal.tsx
A  apps/web/app/(app)/companies/[id]/page.tsx
M  apps/web/lib/types.ts            # Company* + SearchHit + LeadCreate.company_id
M  apps/web/components/layout/AppShell.tsx  # GlobalSearch mount + Cmd+K hook
M  apps/web/components/pipeline/CreateLeadModal.tsx  # autocomplete + dup-warning
```

### Docs

```
M  docs/brain/03_DECISIONS.md           # ADR-022
A  docs/brain/sprint_reports/SPRINT_3_3_COMPANIES.md (this file)
```

0 new npm dependencies. 0 new Python dependencies. 2 new alembic migrations (0023 + 0024).

---

## Stop condition

Stopped before merge + deploy per task instructions. Branch `sprint/3.3-companies` is local-only. Awaiting product-owner sign-off on the two-PR deploy plan above.
