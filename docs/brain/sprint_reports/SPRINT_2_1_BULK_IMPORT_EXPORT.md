# Sprint 2.1 — Bulk Import / Export + AI Bulk-Update

**Status:** ✅ Branch ready for product-owner review · 9/10 groups closed (G5 deferred)
**Period:** 2026-05-08 (single-day sprint)
**Branch:** `sprint/2.1-bulk-import-export` (NOT yet merged to main)
**Commit range:** `46cc6a2..0ad4c86` (G1–G9) + this G10 commit

---

## Goal

Phase 1 + Sprint 2.0 made DrinkX CRM a working pipeline + a system of
record for the conversation. The single biggest day-one ergonomic gap
was data mobility — managers couldn't bulk-load existing leads from
Bitrix24 / Excel, couldn't pull a workspace snapshot to feed an
external AI for batch edits. Sprint 2.1 closes the gap with a focused
import/export surface plus the AI bulk-update loop sketched in PRD §6.14.

No new domains, no new vendors. The scope is intentionally narrow:
**a wide pipe in and out of the existing data model**, with the AI
bulk-update step delegated to whichever LLM the manager prefers
(ChatGPT / Claude / Perplexity) — we don't run the AI part on our
infra, we just round-trip the data.

---

## Groups delivered

| # | Name | Commit | Files | Tests |
|---|---|---|---|---|
| 1 | Schema + import_jobs domain skeleton + credentials encryption | `46cc6a2` | 18 | 12 |
| 2 | Generic parser + column mapper + apply task | `eca1b3d` | 9 | 16 |
| 3 | `/import` wizard frontend (4-step modal) | `484eeae` | 10 | — (build only) |
| 4 | Bitrix24 adapter with auto-detect | `ac2ed90` | 4 | 9 |
| 5 | AmoCRM adapter | — | — | **SKIPPED** per product-owner direction |
| 6 | Streamed export backend (Celery + Redis + status polling) | `3802d9d` | 10 | 10 |
| 7 | «Экспорт» popover on /pipeline + /leads-pool | `046a4a4` | 6 | — (build only) |
| 8 | AI bulk-update snapshot + prompt + 3-step modal | `2abc2a0` | 12 | 6 |
| 9 | Diff engine + apply + bulk_update preview UI | `0ad4c86` | 9 | 11 |
| 10 | Carryover + Sentry + sprint close (this commit) | (this) | ~12 | — |

**Combined backend test suite (Sprint 2.1 deliverables):** 64 mock-only
tests passed, 0 skipped, 0 errors, 0 DB. Spread across:

- `tests/test_credentials_crypto.py` — 6
- `tests/test_import_jobs_service.py` — 6
- `tests/test_import_parsers.py` — 16
- `tests/test_bitrix24_adapter.py` — 9
- `tests/test_exporters.py` — 10
- `tests/test_snapshot.py` — 6
- `tests/test_bulk_update.py` — 11

Combined with Sprint 1.5/2.0 baseline: **94 mock tests passing**.

**Frontend:** `pnpm typecheck` + `pnpm build` clean throughout. 11
routes prerendered. **Zero new npm dependencies** (the streak Sprint 2.0
started survives).

---

## Architecture decisions

### Diff resolution: 3 batched queries, not N round-trips

`compute_diff` for the AI bulk-update flow could have done one DB
round-trip per update item (50–500 items × 5ms = 0.25–2.5s of pure
network sit-time). Instead we collect all `(inn, name, id)` values
upfront, fire three batched `IN (...)` queries, build lookup dicts,
resolve each item in memory. Total: 3 queries regardless of payload
size. Doc'd inline in `diff_engine._batch_load_candidates`.

### Stage moves via diff bypass the gate engine — ADR-007 still satisfied

The gate engine (Sprint 1.2) was designed to prevent managers from
dragging cards across stages without filling in required gate criteria.
The bulk-update flow lets the manager move stages by AI-suggested
diff. Re-prompting for gate criteria per row would defeat the
batch-edit value proposition.

**Resolution:** the manager already approved the diff in the preview
UI before clicking "Apply". That preview IS the human-in-the-loop gate.
ADR-007 ("AI proposes, human approves — always") is satisfied at the
preview level rather than the field level. Documented in
`diff_engine.apply_diff_item`.

### `is_bulk_update_yaml` is a 1KB regex sniff, not a yaml.safe_load

Auto-detect on `/upload` runs against every YAML upload. Parsing 250KB
YAML to decide we don't even want to use the diff engine would burn
~10ms on every file. Cheap regex over the first 1KB looking for
`format: drinkx-crm-update` + `updates:` brings the discriminator down
to <1ms. Full parse only happens after the discriminator commits to
the bulk_update path.

### Per-item commit in apply tasks (real-time UI poll)

Both `bulk_import_run` (G2) and `run_bulk_update` (G9) commit the
session after every row. The UI polls `/api/import/jobs/{id}` every 2s
and sees `processed/succeeded/failed` counters update incrementally.
Trade-off: more commits = more WAL traffic + more chances to lose state
on a worker kill. For the workspace sizes we're handling (≤ 500 rows
typical) the WAL load is negligible and the per-row resilience is worth
it — one bad row never poisons the rest of the batch via session
rollback semantics.

### Redis blob storage for exports (not filesystem)

Export results sit in Redis under `export:{job_id}` with a 1h TTL.
Filesystem would have required pod-level state, the bare-metal Docker
setup doesn't have shared volume mounts, and the bytes are small
(< 500KB typical). Redis is already running for Celery broker —
zero extra infra.

### Separate `redis_bytes.py` client (no `decode_responses`)

The enrichment cache (`app/enrichment/sources/cache.py`) uses
`redis.from_url(..., decode_responses=True)` because it stores JSON
strings. Reusing that client for export blobs would corrupt XLSX/ZIP
payloads (binary → str → binary round-trip eats high bits). G6 added
a separate module-level client without `decode_responses` so blobs
survive untouched. Two clients, two contracts — explicit > clever.

### Credentials at rest: `fernet:` prefix marker, not BYTEA

Sprint 2.0 carryover: `channel_connections.credentials_json` was
plaintext. G1 wraps writes in Fernet encryption with a `fernet:` prefix
in the existing TEXT column. Legacy plaintext rows from Sprint 2.0
still pass through `decrypt_credentials` unchanged (backward compat).
Stub mode (empty FERNET_KEY) falls back to plaintext + one-shot
WARNING; mismatched-mode reads (encrypted row but empty key) hard-fail
rather than silently leak token bytes.

---

## Known issues / risks

1. **E2E UX smoke deferred to staging** — locally we lack the backend
   stack with migrations 0010 + 0011 applied + a real Supabase session
   + a sample bulk_update.yaml from an actual ChatGPT round-trip. All
   verifications in this sprint are structural (`tsc`, `next build`,
   mock pytest); production-readiness checklist below covers the
   smoke run.
2. **`_GENERIC_DOMAINS` (Sprint 2.0 carryover)** — still hardcoded;
   should promote to a per-workspace setting in Sprint 2.2+.
3. **Gmail history-sync 2000-message cap (Sprint 2.0 carryover)** —
   the one-shot backfill still tops out at 2000 messages. Workspaces
   with very dense Gmail history get truncated. Resumable / paginated
   job is Sprint 2.2+.
4. **`pg_dump` cron not configured (Sprint 1.5 carryover)** — DB
   backups are still implicit (Postgres data volume + host snapshots,
   no in-app backup job). Pre-prod blocker for any workspace with
   real customer data; not addressed in 2.1.
5. **Sentry DSNs still empty (partially closed in this G10)** — the
   web-side stub is now in place; backend Sentry init has been live
   since Sprint 1.0. Operator just needs to set `SENTRY_DSN_API` and
   `NEXT_PUBLIC_SENTRY_DSN` in `.env` and (for web) `pnpm add
   @sentry/nextjs`. Telemetry remains off until that lands.
6. **`FERNET_KEY` required pre-deploy** — without it the api logs a
   startup WARNING and falls back to plaintext credentials_json, which
   defeats the entire point of G1 encryption. Generate with:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Add to `/opt/drinkx-crm/infra/production/.env` BEFORE the next
   container restart.
7. **`apps/web/package-lock.json` is stale** — npm lockfile from
   pre-Sprint-1.4 days, never updated since the pnpm migration.
   `pnpm-lock.yaml` is the actual source of truth (see Dockerfile).
   The Next.js build emits a "multiple lockfiles detected" warning
   because of the duplicate. **Follow-up:** delete the npm lockfile
   in Sprint 2.2 G1 housekeeping. Not removed in 2.1 to keep the
   merge surface clean.
8. **AmoCRM adapter (G5) — deferred** to Sprint 2.2+. The same
   `app/import_export/adapters/` plumbing G4 used for Bitrix24 will
   accept a parallel `amocrm.py` module without changes to routers,
   tests, or wizard frontend.

---

## Production readiness checklist

Pre-deploy (run before merging into main):
- [ ] Final review of `sprint/2.1-bulk-import-export` branch
- [ ] Generate `FERNET_KEY` on a trusted machine (see Issue 6 above)
- [ ] Decide whether to commit `apps/web/package-lock.json` removal in
      a G1 follow-up sprint, or do it now as a small cleanup PR

Deploy (in order):
- [ ] `alembic upgrade head` on production DB → applies 0010 (import_jobs +
      import_errors) + 0011 (export_jobs). All reversible.
      In practice this happens automatically via the api Dockerfile
      entrypoint (`uv run alembic upgrade head && uv run uvicorn`),
      same as Sprint 2.0.
- [ ] Add `FERNET_KEY=...` to `/opt/drinkx-crm/infra/production/.env`
- [ ] Restart `api` + `worker` + `beat` containers (env reload). The
      worker registers two new tasks — `run_export` and
      `run_bulk_update` — alongside the existing 4 cron entries.
      Beat schedule unchanged.
- [ ] Verify worker log shows the new tasks registered.

Post-deploy smoke (first 30 min):
- [ ] **Import smoke**: open `/pipeline` → «📥 Импорт» → upload a
      synthetic CSV with company_name + city → mapping auto-suggested
      → confirm → preview shows N create / 0 errors → apply → progress
      bar reaches 100% → manager visits `/leads-pool` and sees the
      newly imported rows.
- [ ] **Export smoke**: same `/pipeline` → «📤 Экспорт» → format=xlsx
      → "Экспортировать" → progress bar → file downloads as
      `leads_YYYY-MM-DD.xlsx` and opens cleanly in Excel/Numbers
      with Cyrillic intact.
- [ ] **AI bulk-update smoke**: `/leads-pool` → «🤖 AI Обновление» →
      Step 1 download snapshot → paste into Claude/ChatGPT alongside
      Step 2 prompt → upload AI's YAML → BulkUpdatePreview shows
      N updates / M creates with per-field deltas → "Применить
      изменения" → ProgressStep → spot-check 1–2 affected leads in
      the Activity Feed for the source attribution.
- [ ] **Bitrix24 auto-detect**: upload a real Bitrix24 CSV export →
      mapping should pre-fill via Cyrillic header heuristics; manager
      doesn't have to specify `?format=bitrix24`.
- [ ] (Optional) Verify the `audit_log` shows entries for any
      bulk-update apply that touched leads (G9 adds Activity rows
      via `apply_diff_item`, but the audit-log emit hooks still need
      a once-over post-deploy).

---

## Files changed (cumulative across G1–G10)

```
apps/api/alembic/versions/20260508_0010_import_jobs.py        (new, 99)
apps/api/alembic/versions/20260508_0011_export_jobs.py        (new, 67)
apps/api/alembic/env.py                                       (+1)
apps/api/app/config.py                                        (+12)
apps/api/app/main.py                                          (+5)
apps/api/app/scheduled/celery_app.py                          (+1)
apps/api/app/scheduled/jobs.py                                (+~250)
apps/api/app/inbox/crypto.py                                  (new, 95)
apps/api/app/inbox/gmail_client.py                            (~10 patch)
apps/api/app/inbox/routers.py                                 (~5 patch)
apps/api/app/import_export/__init__.py                        (existing)
apps/api/app/import_export/adapters/__init__.py               (new, 0)
apps/api/app/import_export/adapters/bitrix24.py               (new, 138)
apps/api/app/import_export/adapters/bulk_update.py            (new, 102)
apps/api/app/import_export/bulk_update_prompt.py              (new, 67)
apps/api/app/import_export/diff_engine.py                     (new, ~620)
apps/api/app/import_export/exporters.py                       (new, ~280)
apps/api/app/import_export/field_map.py                       (new, 109)
apps/api/app/import_export/mapper.py                          (new, 132)
apps/api/app/import_export/models.py                          (new, ~165)
apps/api/app/import_export/parsers.py                         (new, ~225)
apps/api/app/import_export/redis_bytes.py                     (new, 49)
apps/api/app/import_export/routers.py                         (new, ~430)
apps/api/app/import_export/schemas.py                         (new, ~70)
apps/api/app/import_export/services.py                        (new, ~280)
apps/api/app/import_export/snapshot.py                        (new, ~205)
apps/api/app/import_export/validators.py                      (new, 84)
apps/api/pyproject.toml                                       (+2)
apps/api/tests/test_bitrix24_adapter.py                       (new, ~210)
apps/api/tests/test_bulk_update.py                            (new, ~470)
apps/api/tests/test_credentials_crypto.py                     (new, ~155)
apps/api/tests/test_exporters.py                              (new, ~340)
apps/api/tests/test_import_jobs_service.py                    (new, ~225)
apps/api/tests/test_import_parsers.py                         (new, ~280)
apps/api/tests/test_snapshot.py                               (new, ~285)
apps/web/app/(app)/layout.tsx                                 (~5 patch)
apps/web/app/(app)/leads-pool/page.tsx                        (~30 patch)
apps/web/app/(app)/pipeline/page.tsx                          (~10 patch)
apps/web/app/providers.tsx                                    (~5 patch)
apps/web/components/export/AIBulkUpdateModal.tsx              (new, ~265)
apps/web/components/export/ExportPopover.tsx                  (new, ~330; +retro-fix in G8)
apps/web/components/import/ImportWizard.tsx                   (new, ~265; +bulk_update routing in G9)
apps/web/components/import/ImportWizardMount.tsx              (new, 21)
apps/web/components/import/steps/BulkUpdatePreview.tsx        (new, ~340)
apps/web/components/import/steps/MappingStep.tsx              (new, ~225)
apps/web/components/import/steps/PreviewStep.tsx              (new, ~220)
apps/web/components/import/steps/ProgressStep.tsx             (new, ~165)
apps/web/components/import/steps/UploadStep.tsx               (new, ~165)
apps/web/components/pipeline/PipelineHeader.tsx               (~15 patch)
apps/web/lib/download.ts                                      (new, 65)
apps/web/lib/hooks/use-export.ts                              (new, 50)
apps/web/lib/hooks/use-import.ts                              (new, 80)
apps/web/lib/sentry.ts                                        (new, 38)
apps/web/lib/store/pipeline-store.ts                          (+8)
apps/web/lib/types.ts                                         (+~125)
docs/brain/00_CURRENT_STATE.md                                (Sprint 2.1 section)
docs/brain/02_ROADMAP.md                                      (Sprint 2.1 → DONE)
docs/brain/04_NEXT_SPRINT.md                                  (rewritten for Sprint 2.2)
docs/brain/sprint_reports/SPRINT_2_1_BULK_IMPORT_EXPORT.md    (new — this file)
infra/production/.env.example                                 (+9 lines)
pnpm-lock.yaml                                                (root, NEW tracked file)
```

Net: ~8 500 lines added across ~54 files (~40 new, ~14 modified).

---

## Next sprint pointer

→ `docs/brain/04_NEXT_SPRINT.md` — **Sprint 2.2 WebForms**.

Decision context for choosing WebForms over the deferred items
(AmoCRM adapter, Quote builder, Knowledge Base CRUD UI): WebForms is
the lowest-effort highest-impact piece — every landing page DrinkX
runs would benefit from automatic lead capture. The AmoCRM adapter
slots in cheaply once we have a real export to test against; KB CRUD
and Quote can wait for the team to outgrow Sprint 1.3 file-based
config.

The deferred items stay on the Phase 2 envelope — see `02_ROADMAP.md`.
