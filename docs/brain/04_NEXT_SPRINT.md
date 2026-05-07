# Next Sprint: Phase 2 Sprint 2.0 — Inbox + Quote + Forms + Bulk Import

Status: **READY TO START** (after Sprint 1.5 merge / deploy / soft-launch)
Branch: `sprint/2.0-inbox-quote-forms`

## Goal

Phase 1 ended with a working CRM the team can run a sales pipeline in.
Phase 2 turns it into a *system of record* for the whole top-of-funnel — the
inbound side. Ship four cooperating surfaces: Inbox (email + Telegram in one
view), Quote/КП builder, WebForms (public capture endpoints), and Bulk
Import/Export. Plus a real CRUD UI for the Knowledge Base markdown library.

This sprint is intentionally larger than Sprint 1.5 — refine the scope at the
start of the sprint with the product owner before opening the branch.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what Sprint 1.5 left
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope
- `docs/brain/sprint_reports/SPRINT_1_5_POLISH_LAUNCH.md` — Known issues / risks; soft-launch checklist carryover (pg_dump, Sentry, onboarding doc)
- `docs/PRD-v2.0.md` §6 (Inbox), §7 (Quote/КП), §8 (Forms), §9 (Knowledge Base)
- `docs/brain/03_DECISIONS.md` — ADR-007 (no auto-actions), ADR-014 (stub mode), ADR-018 (MiMo)
- Production state at sprint start: 4 app containers running, Sprint 1.5 merged, audit + notifications + digest live; ~216 leads in pool; real Supabase auth on; MiMo+Brave keys live; SMTP still in stub mode

## Scope

### ALLOWED

#### 1. Inbox — Email + Telegram

Per-lead unified message thread. Read-only first, send-from-CRM second.

- **Email read (IMAP)**:
  - Workspace-scoped IMAP credentials in `app/inbox/email_settings` (per-user) — see ADR-007 around what's stored vs OAuth.
  - Polling worker in Celery: pull new messages every 5 min, match to leads by sender/recipient address (lead.email, contacts.email), drop mismatches into a workspace-scoped "unmatched" tray.
  - Dedup by Message-ID. Store full headers + body (text + html if present) in `inbox_messages` table.
- **Email send (SMTP)**:
  - Reuse the SMTP infra from Sprint 1.5 group 5 (aiosmtplib).
  - Send-as the user's configured email; record outbound in same `inbox_messages` table with direction='out'.
  - Optional thread-reply sets `In-Reply-To` + `References` headers for client-side threading.
- **Telegram Business webhook**:
  - One bot per workspace; webhook → `inbox_messages` rows.
  - Match TG user_id → lead via Contact.telegram_url already on the model.
- **Inbox UI** — new top-level route `/inbox`:
  - Left rail: thread list grouped by lead (last-msg-date desc).
  - Right pane: message stream + reply composer (email or TG depending on thread channel).
  - Per-lead inbox tab on Lead Card surfaces the same thread.

Migration: new tables `inbox_messages`, `email_settings` (encrypted IMAP/SMTP creds at rest).

#### 2. Quote / КП builder

- New domain `app/quote`. Data model:
  - `quote` row (lead_id, status, total, currency, valid_until, sent_at, accepted_at)
  - `quote_line_item` row (quote_id, position, product_name, qty, unit_price, discount_percent, line_total)
- REST CRUD; PDF render via WeasyPrint or stdlib HTML → headless Chromium (decide at sprint start; prefer the lighter dep).
- Frontend: Quote tab on Lead Card replaces the existing PilotTab when deal_type is non-pilot. Builder UI = line-item table + totals strip + "Render PDF" + "Send via email" (uses Inbox SMTP).

#### 3. WebForms

- Public capture endpoint `POST /api/forms/{form_id}/submit` — no auth, captcha optional Phase 3.
- Form builder UI — drag-and-drop fields (text / phone / email / select / textarea), preview, copy embed snippet.
- Submissions land in `leads_pool` (assignment_status='pool') with `source='form:{form_id}'` for attribution.

Migration: `forms` + `form_fields` + `form_submissions` tables.

#### 4. Bulk Import / Export

- Import: CSV/XLSX upload → column-mapping screen (drag source-col → target-field) → dry-run preview (first 10 rows + validation errors) → confirm. Reuse the v0.5/v0.6 import script logic (see `crm-prototype/build_data.py`); promote it from a one-off into a workspace-driven feature.
- Export: any list view ([leads-pool], [pipeline]-flat, [audit]) → CSV with current filter applied. Streamed response (no in-memory buffering of large workspaces).

#### 5. Knowledge Base CRUD UI

- Promote the file-based markdown library (Sprint 1.3) to a real CRUD surface. Move content into a `knowledge_articles` table with workspace_id, segment_tags, body_md.
- Frontend: `/knowledge` page — list / view / edit. Markdown render via existing tools (no new dep — use `marked` or `react-markdown` — verify which is already pulled in).
- AI Brief synthesis prompt continues to inject the markdown chunks; the file-based fallback stays as a dev-mode option.

### FORBIDDEN

- Apify integration — Sprint 2.1 candidate
- Push notifications, Telegram bot for managers — Phase 2 Sprint 2.1+
- Multi-pipeline switcher — Phase 2 Sprint 2.1+
- pgvector / vector retrieval — Phase 3
- MCP server / Sales Coach chat — Phase 3
- Visit-card OCR — Phase 3
- New LLM vendors — only the existing fallback chain (MiMo / Anthropic / Gemini / DeepSeek)
- Anything that requires a new payment / subscription account without explicit product-owner approval

## Tests required

- pytest mock-only suites for new domains (inbox, quote, forms) — same harness pattern Sprint 1.5 settled on (sqlalchemy stub at import time, AsyncMock session, no real DB)
- pytest integration: at least one DB-backed test per new table (Postgres-fixture path) for migrations smoke
- Web Playwright skip-if-env: form public submit → lead lands in pool; quote PDF generates without crashing
- Manual: send-from-CRM email lands in inbox of recipient (uses live SMTP, NOT stub) — verify with own mailbox before merge

## Deliverables

- Migrations 0008–0012 (or fewer, depending on schema-bundling decisions at sprint start) applied on production
- `/inbox` route with both channels live in production (real IMAP polling, real Telegram webhook)
- Quote builder usable end-to-end (create → render PDF → send via SMTP)
- One public form created, embed snippet copied, submission lands in pool
- One CSV import + one CSV export run successfully against the live workspace
- `/knowledge` CRUD UI replaces the file-based config at runtime
- `docs/brain/sprint_reports/SPRINT_2_0_INBOX_QUOTE.md` written
- `docs/brain/00_CURRENT_STATE.md` updated
- `docs/brain/02_ROADMAP.md` — Sprint 2.0 → DONE, Sprint 2.1 → NEXT
- `docs/brain/04_NEXT_SPRINT.md` rewritten for Sprint 2.1

## Stop conditions

- All tests pass → report written → committed → push only with explicit product-owner approval
- No scope creep into Sprint 2.1 / Phase 3 items (especially: no Apify, no Telegram bot for managers, no MCP)
- No new payment vendor without explicit discussion (PDF rendering, email relay, etc.)

---

## Recommended task breakdown (~one PR per group, sized for a subagent each)

This list is provisional — refine at sprint start with product owner.

1. **Inbox backend — schema + email IMAP poller** — migrations + Celery worker + dedup
2. **Inbox backend — email SMTP send** — reuse Sprint 1.5 sender, attach to inbox thread
3. **Inbox backend — Telegram Business webhook** — workspace bot config + webhook handler
4. **Inbox frontend — `/inbox` route** — list rail + message pane + reply composer
5. **Inbox frontend — Lead Card inbox tab** — same thread as `/inbox` filtered to one lead
6. **Quote backend — schema + REST + PDF render** — line items, totals, PDF
7. **Quote frontend — builder UI on Lead Card** — line-item table + send-via-email
8. **Forms backend — public submit + storage** — anonymous endpoint + lead creation
9. **Forms frontend — builder + embed snippet** — drag-and-drop fields, preview
10. **Bulk import — column mapper + dry-run** — backend service + frontend wizard
11. **Bulk export — streamed CSV per list view** — applied to leads-pool / pipeline / audit
12. **Knowledge Base CRUD** — table + REST + `/knowledge` UI; move file content into rows
13. **Carryover** — Sprint 1.5 soft-launch open items (Sentry DSNs, pg_dump, onboarding doc, log-volume review)

After all merged: schedule a Phase 2 Sprint 2.0 retro before opening 2.1.

---

## Followups parked from earlier sprints

- **Phase G (Sprint 1.3 follow-on)** — move enrichment orchestrator off FastAPI BackgroundTasks onto Celery; add WebSocket `/ws/{user_id}` for real-time enrichment progress; replace the 2s polling. Sprint 2.0 is a natural home if there's slack.
- **DST-aware daily plan / digest cron** — handle hour-skip and hour-duplicate edge cases.
- **TransferModal user picker** — replace the UUID input with a workspace-users picker once `GET /api/users` (or equivalent) is available.
- **Tab content overflow audit at 375px** — DealTab / ScoringTab / AIBriefTab / ContactsTab / ActivityTab / PilotTab were not exhaustively reviewed in Sprint 1.5 group 6. Point-fix on observation.
- **Cron retry on per-user LLM failure** (Sprint 1.4 carryover).
- **Anthropic 403-from-RU mitigation** — possibly add a reachable-fallback skip rule so the chain doesn't waste a round-trip on every call.
