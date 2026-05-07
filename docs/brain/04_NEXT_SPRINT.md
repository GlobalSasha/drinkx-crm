# Next Sprint: Phase 2 Sprint 2.1 — Bulk Import / Export

Status: **READY TO START** (after Sprint 2.0 merge / deploy / smoke check)
Branch: `sprint/2.1-bulk-import-export` (create from main once 2.0 lands)

## Goal

Phase 1 + Sprint 2.0 made DrinkX CRM a working pipeline + a system of record
for the conversation. The single biggest day-one ergonomic gap left is data
mobility: managers still can't bulk-load existing leads from Bitrix24 / AmoCRM /
Excel, and they can't pull a workspace snapshot to feed an external AI for batch
edits. Sprint 2.1 closes that gap with a focused import/export surface — no new
domains, no new vendors, no new AI capability, just a wide pipe in and out of
the existing data model.

The PRD already sketched the AI-bulk-update loop (§6.14) — *download snapshot →
external AI processes → upload diff → preview → apply*. This sprint is what
makes it real.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what Sprint 2.0 left
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope
- `docs/brain/sprint_reports/SPRINT_2_0_GMAIL_INBOX.md` — known issues / risks; production checklist carryover (cron registered, OAuth client provisioned, migrations applied)
- `docs/PRD-v2.0.md` §6.14 (Bulk operations + AI loop) and §10 (Data model)
- `docs/brain/03_DECISIONS.md` — ADR-007 (no auto-actions, all imports require human confirmation), ADR-009 (package-per-domain), ADR-016 (B2B model is the target)
- Production state at sprint start: 4 app containers + 4 cron entries (after Sprint 2.0 merge) running, ~216 leads in pool, real Supabase auth on, Gmail inbox sync live for at least one manager (smoke step)
- `crm-prototype/build_data.py` — the v0.5/v0.6 import logic that lives in the prototype repo. Promote, don't duplicate.

## Scope

### ALLOWED

#### 1. Import — Excel / CSV / YAML / JSON

- New domain `app/import_export` (the package already exists empty — fill it).
- File upload endpoint `POST /api/import/upload` — accepts multipart, parses
  with `openpyxl` (XLSX), stdlib `csv` (CSV), `pyyaml` (YAML), stdlib `json`
  (JSON). Stored as a temporary parsed payload in Redis (TTL 1h) keyed by an
  import-job UUID. No DB row yet.
- Format detection by file extension first, MIME type second. Rejects
  anything else with a clear error.
- Column mapping screen — drag/drop or dropdowns from source columns
  → target Lead fields (company_name, segment, city, email, phone,
  website, inn, deal_type, priority, score). Guess obvious mappings via
  fuzzy header match (`company name` / `Компания` / `Название` →
  `company_name`).
- Dry-run preview — first 10 mapped rows + a validation summary
  (missing required, enum-out-of-range, duplicate by inn/email/website).
  Validation runs on the full set, preview shows the worst-case rows.
- Confirm step — runs in Celery (`bulk_import_run(job_id, user_id)`)
  so a 5000-row import doesn't tie up the request thread. Status polled
  via the same job-id pattern Sprint 1.3 used.
- New tables: `import_jobs(id, workspace_id, user_id, status, format,
  source_filename, total_rows, processed, succeeded, failed, error_summary,
  created_at, finished_at)` + `import_errors(job_id, row_number,
  field, message)`.

#### 2. Import — Bitrix24 / AmoCRM dump format

- Two new format adapters: `app/import_export/adapters/bitrix24.py`,
  `app/import_export/adapters/amocrm.py`.
- Each adapter knows the canonical export shape from those CRMs (Bitrix24:
  XLS / CSV with cyrillic column names; AmoCRM: JSON with nested objects
  for contacts / leads / pipelines).
- Adapter returns a normalized list-of-dicts with our internal
  field names — the column-mapping screen is bypassed when the
  upload is recognized as a known format. Manager confirms the
  dry-run preview as usual.
- Contacts are imported as `Contact` rows alongside the parent Lead
  (Bitrix24 / AmoCRM both ship contacts with leads — we'd lose data
  if we dropped them).

#### 3. Export — streaming CSV / XLSX / JSON / YAML / Markdown ZIP

- `GET /api/export/leads?format=xlsx&filter=...` — streamed response
  (no in-memory buffering of large workspaces). XLSX uses `openpyxl`
  in write-only mode. CSV / JSON / YAML use stdlib + generators.
  Markdown ZIP: one `.md` file per lead with full Activity Feed +
  AI Brief, zipped with stdlib `zipfile` (write streaming).
- Filters re-use the existing Lead list query (`?stage_id`,
  `?segment`, `?city`, `?priority`, `?deal_type`, `?q`).
- Three preset views accessible from the existing list pages:
  current pipeline, all leads, current filter. "Export" button on
  `/pipeline` + `/leads-pool`.

#### 4. AI bulk-update flow

- `POST /api/export/snapshot` — produces a workspace snapshot in
  YAML (one document per lead, with all fields + last 5 activities + AI
  Brief result_json). Manager downloads, feeds to ChatGPT / Claude / etc.
  externally. **No AI runs server-side for this flow** — that's the
  whole point: leverage external models without our cost/quotas.
- `POST /api/import/bulk-update` — accepts the AI's response (same YAML
  schema). Diff engine compares each row to the live Lead state and
  produces a per-field change list. Preview UI shows the diff with
  per-field accept/reject toggles. Apply runs in Celery same as #1.
- Audit log emits one `lead.bulk_update` row per applied change with
  `delta_json={field: {from, to}, source: "bulk_ai", job_id: ...}`.

### FORBIDDEN

- Telegram Business inbox — Sprint 2.2+ candidate
- Email reply / send (gmail.send scope) — Sprint 2.2+ candidate
- Quote / КП builder — deferred from 2.0 envelope, Sprint 2.2+
- WebForms / public capture endpoints — Sprint 2.2+
- Knowledge Base CRUD UI — Sprint 2.2+
- Apify integration — Sprint 2.2+ candidate
- Push notifications, Telegram bot for managers — Phase 2.2+
- Multi-pipeline switcher — Phase 2.2+
- pgvector / vector retrieval — Phase 3
- MCP server / Sales Coach chat — Phase 3
- Visit-card OCR — Phase 3
- New LLM vendors — only the existing fallback chain (MiMo / Anthropic / Gemini / DeepSeek)
- Synchronous AI calls during bulk-update apply — that's intentionally manager-driven externally
- Anything that requires a new payment / subscription account without explicit product-owner approval
- New npm dependencies (we got to ship Sprint 2.0 with zero — keep the streak)

## Tests required

- pytest mock-only suites for new domains (import_export adapters, diff engine,
  bulk_import_run service) — same harness pattern Sprint 1.5 / 2.0 settled on
  (sqlalchemy stub at import time, AsyncMock session, no real DB)
- pytest integration: at least one DB-backed test per new table (`import_jobs`,
  `import_errors`) for migrations smoke
- File-format roundtrip tests: write XLSX → read XLSX → assert fields
  preserved; same for YAML / JSON / Markdown ZIP. Mock-only, in-memory.
- Bitrix24 + AmoCRM adapter tests against fixture files (a few rows each)
  checked into `tests/fixtures/import/`. Don't commit real customer data.
- Manual: end-to-end import of a 500-row Bitrix24 dump on staging before merge

## Deliverables

- Migrations 0010–0012 (or fewer, depending on schema-bundling at sprint start) applied on production
- `/import` and `/export` routes with the column-mapper + dry-run preview UI
- One CSV / XLSX import + one Bitrix24 import run successfully against the live workspace (smoke step)
- Streamed XLSX export of full lead pool (~216 rows) verified to fit in memory limits
- AI bulk-update loop demoed end-to-end: download snapshot → manual ChatGPT pass → upload + preview → apply at least 5 changes
- `docs/brain/sprint_reports/SPRINT_2_1_BULK_IMPORT.md` written
- `docs/brain/00_CURRENT_STATE.md` updated
- `docs/brain/02_ROADMAP.md` — Sprint 2.1 → DONE, Sprint 2.2 → NEXT
- `docs/brain/04_NEXT_SPRINT.md` rewritten for Sprint 2.2

## Stop conditions

- All tests pass → report written → committed → push only with explicit product-owner approval
- No scope creep into Sprint 2.2 / Phase 3 items (especially: no Apify, no Telegram bot, no MCP, no Quote/КП, no WebForms)
- No new payment vendor without explicit discussion
- No new LLM vendor (the AI part runs *off* our stack — that's the whole design)

---

## Recommended task breakdown (~one PR per group, sized for a subagent each)

This list is provisional — refine at sprint start with product owner.

1. **Schema + import_jobs domain skeleton** — migration + ORM + empty service stubs + Celery task wired
2. **Generic CSV / XLSX / YAML / JSON parser + column mapper backend** — file upload, parsing, fuzzy-match heuristics, dry-run validation
3. **Frontend `/import` wizard** — upload → mapping screen → dry-run preview → confirm → progress poll
4. **Bitrix24 adapter** — known-format detection, normalized output, contacts preserved, fixture-based tests
5. **AmoCRM adapter** — same shape as #4
6. **Streamed export** — `GET /api/export/leads` with `format=xlsx|csv|json|yaml|markdown_zip` + filter passthrough
7. **Frontend export buttons** — "Export" CTA on `/pipeline`, `/leads-pool`, `/audit`; format picker
8. **AI bulk-update — snapshot endpoint** — YAML producer with full lead + activity + AI Brief embed
9. **AI bulk-update — diff engine + preview UI** — backend diff, frontend per-field accept/reject, apply via Celery
10. **Carryover** — Sprint 2.0 production-readiness items still open (`credentials_json` encryption is the big one), Sprint 1.5 soft-launch carryovers (Sentry DSNs, pg_dump, onboarding doc)

After all merged: schedule a Phase 2 Sprint 2.1 retro before opening 2.2.

---

## Followups parked from earlier sprints

- **Sprint 2.0 carryovers** — `credentials_json` encryption (security
  TODO), 2000-msg history-sync cap (resumable / paginated job),
  `_GENERIC_DOMAINS` per-workspace setting, `pnpm-lock.yaml` housekeeping
- **Phase G (Sprint 1.3 follow-on)** — move enrichment off FastAPI
  BackgroundTasks onto Celery (infra exists from Sprint 1.4); WebSocket
  `/ws/{user_id}` for real-time enrichment progress; replace the 2s polling
- **DST-aware daily plan / digest cron** — handle hour-skip and
  hour-duplicate edge cases
- **TransferModal user picker** — replace the UUID input with a
  workspace-users picker once `GET /api/users` (or equivalent) lands
- **Tab content overflow audit at 375px** — DealTab / ScoringTab /
  AIBriefTab / ContactsTab / ActivityTab / PilotTab were not exhaustively
  reviewed in Sprint 1.5 group 6. Point-fix on observation
- **Cron retry on per-user LLM failure** (Sprint 1.4 carryover)
- **Anthropic 403-from-RU mitigation** — possibly add a reachable-fallback
  skip rule so the chain doesn't waste a round-trip on every call
