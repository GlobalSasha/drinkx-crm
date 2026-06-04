# Next Sprint — Odoo-reuse follow-ups + UI consistency

**Status:** 🟢 READY TO START (a fresh session begins here)
**Prev:** Odoo-reuse arc — 8 PRs (#102–#109) shipped. Full record in `00_CURRENT_STATE.md`
(section «Odoo-reuse arc + test CI (2026-06-04)»). Sprint 3.5 (Production Polish v2)
and Website Leads Intake are done; their record is in git history + `00_CURRENT_STATE.md`.

---

## Context — read before touching code

- **Backend already shipped (in prod):** phone E.164 normalization; lead duplicate
  **detection** (`GET /leads/{id}/duplicates`) + **merge** (`POST /leads/{id}/merge`,
  soft/reversible via `leads.merged_into_id`); UTM dictionaries auto-resolved on form
  submit (`leads.utm_source_id/medium_id/campaign_id`). New code lives in
  `app/common/phone.py`, `app/common/email.py`, `app/leads/dedup.py`, `app/utm/`.
- **Alembic head `0045`. Next free index `0046`.**
- **Test CI now exists** — `.github/workflows/test.yml` (postgres:16). Every PR touching
  `apps/api/**` runs pytest. Write DB-backed integration tests with the `db` / `workspace`
  fixtures + `@skip_no_pg` (see `tests/test_utm.py`, `tests/test_lead_merge.py` for the
  pattern). Push → watch the «Tests (api)» check green before merging.
- **Merge to `main` auto-deploys to prod.** Always: branch → PR → CI green → merge.

---

## Scope (gated — pick top-down)

### G1 — Dedup merge UI  ⭐ highest value
The merge backend is live but unreachable from the app. Build the human-in-the-loop UI.
- [x] On LeadCard, a «Найти дубли» action → `GET /leads/{id}/duplicates` → list candidates
      (company, email domain, phone, city). Empty → nothing shown.
- [x] «Объединить» → confirmation modal: the current lead is the master; user picks which
      duplicates → `POST /leads/{id}/merge {duplicate_ids}` → toast + refresh.
      **Never auto-merge** (anti-pattern #4 — human confirms).
- [x] On a lead that absorbed dups, show a «← объединён из N» note (read it from the
      `system` audit Activity the merge writes).
- Frontend only (backend done). Pre-PR: `npm run typecheck` + `npm run lint` + `pnpm build`.

### G2 — UTM channel analytics
UTM dims now land on leads. Surface «какой канал приносит сделки».
- [x] `GET /api/leads/utm-stats` (or under `/forms`) — GROUP BY source → `{leads, won, sum}`.
      DB-backed test.
- [x] A «Каналы привлечения» table card on `/forecast` (or `/forms`).

### G3 — Backfill normalized columns
Existing rows have NULL `phone_e164` / `email_normalized` / `email_domain_criterion`
(they fill only on next save). UTM ids likewise only on new form leads.
- [x] One-off Celery task (or `scripts/…`) iterating leads + contacts, re-deriving the keys
      via `app.common.phone.to_e164` + `app.common.email.normalize_email/email_domain_criterion`.
      Idempotent; batch-commit. DB-backed test on a few rows.
      Done: `app/common/backfill.py` core + `app.scheduled.jobs.backfill_normalized_keys`
      manual-trigger task + 4 DB-backed tests. UTM-id backfill left out of scope (needs the
      form_submissions.utm_json join — separate follow-up if wanted).

### G4 — UI consistency fixes 3–5 (from the UI plan)
- [x] One shared empty-state component used everywhere (replace ad-hoc divs e.g. `/team`).
      Done: `/team` access-denied + no-members states now use the shared `Empty`.
- [x] Lint rule banning arbitrary Tailwind sizes (`text-[28px]`, `border-[1.5px]`) — use the scale.
      Done: local `drinkx/no-arbitrary-px` at **warn** level (flags new ones, doesn't break the
      build). The ~235 pre-existing usages are deliberately left untouched — see BACKLOG #3.
- [~] Break the 617-line `LeadCard` header + the `leads/[id]` / `companies/[id]` detail pages
      into reusable sections and wrap them in `PageContainer` — **deferred to BACKLOG #3**.
      These are bespoke full-bleed layouts (own sticky header); wrapping/splitting risks visual
      regressions on the most-used screen with no E2E. Do it as its own PR with preview checks.

### G5 — Finish the 2 quarantined tests  (needs a local Postgres)
In `apps/api/tests/conftest.py` → `_KNOWN_PRE_EXISTING_FAILURES`:
- [ ] `test_inbox_matcher::test_processor_creates_activity_on_high_confidence_match` — the
      attach_to_lead path fans out to Automation Builder + Celery (imported in-function in
      `app/inbox/processor.py`); the broad `try/except` swallows the failure. Mock the
      collaborators (`safe_evaluate_trigger`, `collect_pending_email_dispatches`,
      `lead_agent_refresh_suggestion`) so the path returns True, then remove the quarantine entry.
- [ ] `base_update/test_e2e::test_e2e_extract_match_apply` — `run_extract_and_match` now creates
      0 leads (final assert `len(leads) >= 1` fails). Find where lead creation moved (likely
      `run_apply_resolutions`) and fix the assertion/flow, then un-quarantine.
- Run locally: `cd apps/api && TEST_DATABASE_URL=postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test uv run pytest`
  (needs a local Postgres — Docker `infra/docker/docker-compose.yml` or a `drinkx_test` DB).

---

## Pre-PR gates (per CLAUDE.md)

- **Frontend:** `npm run typecheck` + `npm run lint` + `pnpm build` (Next.js 15 build-time
  checks only fire during `next build`).
- **Backend:** `python -m py_compile` touched modules + `uv run alembic heads` (must be a
  single head) + push → watch the «Tests (api)» CI check go green.

## Stop-rules / anti-patterns
- Never auto-merge duplicates — human confirms (anti-pattern #4).
- Don't add entries to the xfail quarantine — fix the test instead.
- One PR per logical change; remember merge-to-`main` = prod deploy.
