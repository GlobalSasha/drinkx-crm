# Sprint 2.0 — Gmail Inbox sync

**Status:** ✅ Branch ready for product-owner review · 7/7 groups closed
**Period:** 2026-05-07 → 2026-05-08 (two-day sprint)
**Branch:** `sprint/2.0-gmail-inbox` (NOT yet merged to main)
**Commit range:** `8745394..ba9c85a` (G1–G6) + this G7 commit

---

## Goal

Take what was a "system of record for the pipeline" out of Phase 1 and turn
it into a **system of record for the conversation**. One channel only —
Gmail read-only — so the team can see real correspondence on every lead
card without leaving the CRM, and so the AI Brief synthesizes against
actual customer signal instead of just public web data.

Scope was deliberately narrowed to Gmail (no Telegram, no IMAP, no SMTP
send) so we could ship a working end-to-end loop in one sprint. Telegram
Business + email reply land in Sprint 2.1+.

---

## Groups delivered

| # | Name | Commit | Files | Tests |
|---|---|---|---|---|
| 1 | Gmail OAuth + token storage + GmailClient | `8745394` | 10 (api+infra) | — (structural) |
| 2 | Celery history sync + 5-min incremental polling | `39b3c6f` | 4 (api) | — (structural) |
| 3 | Matcher + processor + migration 0009 + ADR-019 | `762383c` | 10 (api+docs) | 9 (mock-only) |
| 4 | Inbox UI — REST + `/inbox` page + sidebar badge | `64a8611` | 7 (api+web) | — (build only) |
| 5 | Email rendering in Lead Card Activity Feed | `71f0470` | 3 (api+web) | — (build only) |
| 6 | Email context in AI Brief synthesis | `ba9c85a` | 2 (api) | 3 (mock-only) |
| 7 | Tests + sprint close (this commit) | (this) | 7 (tests+docs) | 6 (mock-only) |

**Combined backend test suite (Sprint 2.0 deliverables):** 18 passed, 0
skipped, 0 errors, 0 DB. Spread across:

- `tests/test_inbox_matcher.py` — 9 tests (matcher + processor)
- `tests/test_email_context_in_brief.py` — 3 tests (email-context injection)
- `tests/test_inbox_services.py` — 6 tests (confirm + dismiss + 404 guard)

Combined with the Sprint 1.5 baseline mock suites (audit 7, email_digest 5)
the full mock-only run is **30 passed, 0 skipped, 0 DB**. No regressions.

**Frontend:** `pnpm typecheck` + `pnpm build` clean throughout. 11 routes
prerendered including the new `/inbox` (7.59 kB). No new npm dependencies.

---

## What shipped

### Group 1 — OAuth + GmailClient (`8745394`)

- Migration `0008_channel_connections` — workspace_id (CASCADE) / user_id
  (CASCADE, NULLABLE for workspace-scoped channels) / channel_type(40) /
  credentials_json (TEXT) / status(20) / extra_json (JSON) /
  last_sync_at / created_at / updated_at + 2 indexes
  ((workspace_id, channel_type, status) and (user_id, channel_type)).
- `app/inbox/gmail_client.py` — `GmailClient` async wrapper over
  `google-api-python-client`. Sync API calls run via `asyncio.to_thread`.
  Auto-refresh via `_ensure_fresh()`; rotated JSON exposed to caller via
  `refreshed_credentials_json()` so the persistence layer can write back
  the new access token. Methods: `list_messages` (auto-paginate up to
  `max_results=500`), `get_message`, `get_history`, `get_profile`. All
  fail-soft — HTTP / Auth / unknown errors return `[]` or `None` and log.
- `app/inbox/oauth.py` — `build_consent_url(state)`,
  `exchange_code_for_credentials(code)`, plus a tiny HMAC-SHA256
  `state` token (`user_id.exp` signed with `SUPABASE_JWT_SECRET`,
  10-min TTL). The callback verifies the state to recover identity
  without our Bearer header (browser arrives at `/api/inbox/gmail/callback`
  via Google's redirect, no Authorization header).
- `app/inbox/routers.py` — `POST /api/inbox/connect-gmail` (returns
  `{redirect_url}`) + `GET /api/inbox/gmail/callback` (exchanges code,
  upserts ChannelConnection, dispatches `gmail_history_sync`).
- New env vars in `config.py` + `.env.example`: `API_BASE_URL`,
  `FRONTEND_BASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `GMAIL_SCOPES`, `GMAIL_HISTORY_MONTHS`, `GMAIL_SYNC_INTERVAL_MINUTES`,
  `GMAIL_MAX_BODY_CHARS`. Three new Python deps: `google-auth`,
  `google-auth-oauthlib`, `google-api-python-client`.

### Group 2 — Celery sync tasks (`39b3c6f`)

- `app/inbox/sync.py` — async cores:
  - `history_sync_for_user(user_id)` — one-shot backfill via Gmail
    `q="after:YYYY/MM/DD"`, capped at 2000 messages. Calls
    `processor.process_message` per message, per-message try/except, then
    seeds `extra_json.last_history_id` from `users.getProfile.historyId`.
  - `incremental_sync_for_all()` — every-5-min tick. Walks every active
    Gmail ChannelConnection, calls `_incremental_for_one`. Per-user
    failures are caught + rolled back; the tick continues.
  - `_incremental_for_one` — uses Gmail History API, dedups within the
    batch, walks `messagesAdded`, processes each, updates the cursor.
  - `_persist_credentials` — writes refreshed JSON back to the row after
    every tick, so a long-running channel doesn't accumulate expired
    access tokens.
- `app/scheduled/jobs.py` — two new Celery tasks: `gmail_history_sync`
  (bespoke audit wrapper because the job needs `user_id`),
  `gmail_incremental_sync` (uses the standard `_run` wrapper). Both use
  the per-task NullPool engine pattern from Sprint 1.4.
- `app/scheduled/celery_app.py` — beat entry
  `gmail-incremental-sync` at `crontab(minute="*/{GMAIL_SYNC_INTERVAL_MINUTES}")`
  (defaults to `*/5`).

### Group 3 — Matcher + processor + migration 0009 (`762383c`)

- Migration `0009_inbox_items_and_activity_email`:
  - `activities` adds `gmail_message_id VARCHAR(200)` (partial-unique
    index `WHERE gmail_message_id IS NOT NULL`), `gmail_raw_json JSON`,
    `from_identifier VARCHAR(300)`, `to_identifier VARCHAR(300)`.
    `subject` widened 300 → 500.
  - `inbox_items` table: workspace+user FKs, `gmail_message_id UNIQUE
    NOT NULL`, from_email, to_emails (JSON), subject, body_preview,
    received_at, direction, status (default `'pending'`),
    suggested_action JSON, created_at. Indexes: (workspace_id, status,
    received_at DESC) and (user_id, status).
- ORM updates: `Activity` gains the four new columns + `subject` widened;
  new `InboxItem` model with explicit `created_at` (no TimestampedMixin
  per spec). New `InboxItemStatus` / `EmailDirection` enums.
- `app/inbox/matcher.py` — `MatchResult` dataclass + `match_email`:
  contact_email (1.0) → lead_email (0.95) → unique-website-domain (0.7)
  → none (0.0). 18-entry `_GENERIC_DOMAINS` set (gmail.com, yandex.ru,
  mail.ru, etc.) skips the domain step entirely. Domain match requires
  exactly ONE lead in the workspace (`limit(2)` + ambiguity check).
  `auto_attach` threshold = 0.8.
- `app/inbox/email_parser.py` — stdlib-only helpers
  (`parse_email_address`, `parse_email_list`, `parse_rfc2822`,
  `extract_body`, `is_sent_message`, `headers_to_dict`). Walks Gmail
  multipart `payload.parts` tree, prefers `text/plain`, falls back to
  stripped `text/html`, then `message.snippet`. Handles urlsafe
  base64 + padding.
- `app/inbox/processor.py` — replaces the G2 stub. Flow: extract → dedup
  (Activity + InboxItem both checked) → match → branch on
  `match.auto_attach`. High-confidence → Activity row scoped to the
  matched lead with all email columns + `payload_json` carrying
  `match_type` + `match_confidence`. Low/no match → InboxItem
  (status='pending') + `celery_app.send_task('app.scheduled.jobs.generate_inbox_suggestion', args=[id])`.
  Raw payload saved only if < 50KB. Body capped at `GMAIL_MAX_BODY_CHARS`
  (10 000). Whole body wrapped in try/except + `session.rollback()`.
- `app/scheduled/jobs.py` — `generate_inbox_suggestion(item_id)` Celery
  task. Loads InboxItem, builds prompt (DrinkX context + from_email +
  subject + body_preview), calls `complete_with_fallback(task_type=TaskType.prefilter)`
  (routes to MiMo Flash). JSON-only output, parsed with try/except.
  On any failure, `suggested_action` stays `NULL`.
- `docs/brain/03_DECISIONS.md` — **ADR-019** added.
- `tests/test_inbox_matcher.py` — 9 mock-only tests.

### Group 4 — Inbox UI (`64a8611`)

Backend:
- `app/inbox/schemas.py` — InboxItemOut / InboxPageOut / InboxConfirmIn /
  InboxCountOut.
- `app/inbox/services.py` — `list_inbox`, `count_pending`, `confirm_item`
  (match_lead | create_lead | add_contact, each writing an `audit.log`
  row), `dismiss_item`. ADR-019 invariant baked into
  `_activity_kwargs_from_item` — Activity is lead-scoped, `user_id` =
  audit trail. `create_lead` falls back to `from_email` when
  `company_name` is empty so a manager can confirm without typing.
  `add_contact` uses `contact_name or from_email` as the contact name.
- `app/inbox/routers.py` extended with `GET /api/inbox`,
  `GET /api/inbox/count`, `POST /api/inbox/{id}/confirm`,
  `POST /api/inbox/{id}/dismiss`. All scoped to caller's workspace.
  404 on cross-workspace lookups, 400 on bad `action`.

Frontend:
- `lib/types.ts` — InboxItemOut, InboxPageOut, InboxConfirmIn,
  InboxCountOut, SuggestedAction, InboxItemStatus, EmailDirection,
  InboxAction.
- `lib/hooks/use-inbox.ts` — `useInboxCount` (30s poll, matches bell
  cadence), `useInboxPending(page)`, `useConfirmItem`, `useDismissItem`,
  `useConnectGmail`.
- `app/(app)/inbox/page.tsx` — empty state with "Подключить Gmail" CTA;
  rows with direction icon + from + subject + body preview + relative
  time; AI-suggestion chip with confidence pill; action buttons (Создать
  карточку modal with editable prefilled company name, Привязать к лиду
  search dropdown over existing leads with "Добавить как письмо" /
  "Добавить как контакт" sub-menu, Игнор with optimistic hide).
  Pagination prev/next, page_size 20. Callback banner reads `?status=`
  from query string (Suspense-wrapped to satisfy Next 15
  `useSearchParams` CSR-bailout).
- `components/layout/AppShell.tsx` — "Входящие" promoted out of the
  disabled list with red-dot pending badge (same `99+` cap as the bell).
  Visible to all roles.

### Group 5 — Email rendering in Activity Feed (`71f0470`)

- `apps/api/app/activity/schemas.py` — `ActivityBase` gains
  `from_identifier`, `to_identifier`, `gmail_message_id`. Existing
  `channel`, `direction`, `subject`, `body` already present.
- `apps/web/lib/types.ts` — `ActivityOut` mirrors the new fields.
- `apps/web/components/lead-card/ActivityTab.tsx` — new
  `EmailActivityItem` branch in the dispatch (before `stage_change`).
  Direction icon (← inbound blue / → outbound emerald — same
  `lucide-react` arrows used in `/inbox`), `from_identifier` + dateStr +
  timeStr in the header. Bold subject, `(без темы)` fallback. Body
  preview (`body.slice(0, 200) + "…"`) with `Показать полностью` /
  `Свернуть` toggle (local `useState`, `ChevronDown` rotates). Whitespace
  preserved (`whitespace-pre-wrap`). No body row when `activity.body`
  is null/empty. Same canvas card style as the default activity item.

### Group 6 — Email context in AI Brief (`ba9c85a`)

- `apps/api/app/enrichment/orchestrator.py`:
  - New `_load_email_context(session, lead_id, *, limit=10) -> str`.
    `SELECT Activity WHERE lead_id=... AND type='email' ORDER BY
    created_at DESC LIMIT 10`. ADR-019 invariant — query is
    lead-scoped only, no `Activity.user_id` filter. Formats result as
    `[← Входящее] / [→ Исходящее] Тема: ... | body[:200]` lines under
    `Переписка с клиентом (последние письма):` preamble. Newlines
    flattened so each email stays one prompt line.
  - New `_format_email_section(email_ctx)` wraps the (already-truncated)
    block in the `### Переписка с клиентом` system-prompt section with
    the LLM directive *"Используй переписку как сигнал реального интереса
    или возражений. Не пересказывай письма — только учитывай как контекст
    для оценки."*
  - `run_enrichment` injection between KB and `SYNTHESIS_SYSTEM`,
    capped at `EMAIL_CONTEXT_MAX_CHARS = 2000`.
- `tests/test_email_context_in_brief.py` — 3 mock-only tests.

### Group 7 — Tests + sprint close (this commit)

- `tests/test_inbox_services.py` — 6 mock-only tests covering
  `confirm_item` (match_lead / create_lead / fallback to from_email /
  add_contact / 404 guard) and `dismiss_item`.
- ADR-019 reformatted to the spec template (Date / Status / Decision /
  Implementation / Implemented in).
- This sprint report.
- `docs/brain/00_CURRENT_STATE.md` updated.
- `docs/brain/02_ROADMAP.md` updated.
- `docs/brain/04_NEXT_SPRINT.md` rewritten for Sprint 2.1.

---

## Architecture decisions

### ADR-019 — Email ownership model (lead-scoped, not manager-scoped)

Activity.user_id records *which manager's mailbox sourced the email* —
audit trail, not visibility filter. Every team member sees every email on
a lead regardless of who wrote it. Rationale: B2B context is a company
asset, transfers shouldn't lose history, AI Brief synthesizes against
the full thread.

Implementation: every read path (`/api/leads/{id}/activities`, AI Brief
`_load_email_context`) scopes by `lead_id` only. `confirm_item` writes
Activity rows with `user_id=current_user.id` (audit) but the read side
ignores that column. Existing notifications stay per-user — independent
mechanism.

This is the single most consequential decision in Sprint 2.0; everything
else (matcher confidence threshold, sync cadence, OAuth flow) is
implementation detail. ADR-019 is what makes this a real CRM and not
"my Gmail's view of the lead."

### Variant 1 ownership = no per-user channels in v1

ChannelConnection has `user_id NULLABLE` so that a future v2 workspace-
level Gmail (one bot mailbox per workspace) drops in without a schema
change, but v1 ships per-user only. Each manager connects their own
Gmail account; sync runs in their identity. This matches how the team
actually corresponds with prospects today and avoids the "shared mailbox
permissions" mess we'd hit otherwise.

### Other decisions worth recording

- **Gmail History API, not Push/Pub-Sub.** Polling every 5 min via Celery
  beat. Trades a few minutes of sync latency for not having to operate a
  webhook receiver, manage Pub/Sub subscriptions, or open another
  externally-routable surface. Fine for a 5-person sales team.
- **6 months of history on first connect.** Configurable via
  `GMAIL_HISTORY_MONTHS`. 2000-message cap on the backfill keeps the
  one-shot run bounded.
- **Auto-attach threshold = 0.8.** Below that, message goes to
  `inbox_items` for human review (ADR-007: AI proposes, human approves).
  Domain-only matches (0.7) never auto-attach.
- **`_GENERIC_DOMAINS` hardcoded set.** Generic mailbox providers
  (gmail.com / yandex.ru / mail.ru / etc.) skip the domain step
  entirely — otherwise every random gmail address would attach to
  whatever lead happens to share the domain in its `website` field.
- **Raw payload kept inline if < 50KB.** Bigger messages drop the
  `gmail_raw_json` field and only the parsed columns survive — keeps row
  bloat bounded and prevents 5MB attachments from crashing the parser.

---

## Known issues / risks

1. **`credentials_json` stored as plaintext** — TODO Sprint 2.1: encrypt
   at rest with Fernet/KMS. Migration uses TEXT, not BYTEA, so the swap
   is a code change only. Documented in the migration body and the
   `ChannelConnection` ORM docstring.
2. **2000-message cap on history sync** — soft guard. If a user has more
   than 2000 emails in 6 months we keep the most recent 2000 and never
   get to the older ones. Could paginate further or split into a
   resumable job in 2.1.
3. **`generate_inbox_suggestion` not yet bench-tested with real MiMo** —
   the structural code path is right (TaskType.prefilter → Flash SKU per
   ADR-018) but we haven't observed live `suggested_action` rows yet.
   First smoke check is the post-deploy step "Проверить inbox_items
   после первого sync".
4. **`_GENERIC_DOMAINS` hardcoded** — fine for a B2B-coffee-machines
   workspace where individual gmail.com addresses are never actual
   prospects. If we ever sell this CRM to a workspace whose product
   *targets* gmail.com freelancers, this becomes a per-workspace
   setting. TODO 2.1.
5. **`pnpm-lock.yaml` not tracked** in the repo — `pnpm install` during
   G4 generated one at the worktree root. The repo historically tracked
   `apps/web/package-lock.json`. Housekeeping for a future PR — does
   not affect Sprint 2.0 functionality.
6. **Migrations 0008 + 0009 not yet applied on production** — they ship
   with the merge. The deploy step has to run `alembic upgrade head`
   before traffic hits the new code, otherwise the first
   `/api/inbox/count` call will explode on the missing `inbox_items`
   table.
7. **OAuth client config not yet provisioned** — `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET` env vars need to be set on production. We can
   reuse the existing Supabase Google OAuth app credentials; Google will
   show a fresh consent screen because the requested `gmail.readonly`
   scope differs from Supabase's sign-in scopes.
8. **DST not handled** for the 5-min cron — same as Sprint 1.4: it ticks
   on UTC every 5 min and that's fine. No timezone-local gating.
9. **No reply / compose** — Phase 2.1.

---

## Production readiness checklist

Pre-deploy (run before merging into main):
- [ ] Final review of `sprint/2.0-gmail-inbox` branch
- [ ] Decide whether to commit `pnpm-lock.yaml` as a housekeeping step

Deploy (in order):
- [ ] `alembic upgrade head` on production DB → applies 0008 + 0009
      (both reversible)
- [ ] Add `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` to
      `/opt/drinkx-crm/infra/production/.env`
- [ ] Add `API_BASE_URL=https://crm.drinkx.tech` +
      `FRONTEND_BASE_URL=https://crm.drinkx.tech` to the same `.env`
      (defaults to localhost otherwise)
- [ ] Add `https://crm.drinkx.tech/api/inbox/gmail/callback` to the
      Google OAuth client's authorized redirect URIs
- [ ] Restart `api` + `worker` + `beat` containers (env reload)
- [ ] Verify `beat` log shows the new `gmail-incremental-sync` cron
      registered

Post-deploy smoke (first 30 min):
- [ ] One manager (yourself) clicks **Подключить Gmail** in `/inbox`
- [ ] Google consent screen renders, scopes are `gmail.readonly`
- [ ] Callback redirects to `/inbox?connect=gmail&status=ok`
- [ ] `gmail_history_sync` runs in the worker — check logs for
      `gmail.history_sync.start` → `gmail.history_sync.done`
- [ ] After ~3 min, `inbox_items.status='pending'` rows exist for
      unmatched senders; some `activities.gmail_message_id` rows for
      auto-matched ones
- [ ] `Sidebar → Входящие` badge shows pending count
- [ ] Open a lead that received an auto-matched email — Activity Feed
      renders the email row with direction icon, subject, body preview,
      "Показать полностью" toggle works
- [ ] Trigger AI Brief regeneration on that lead — synthesis prompt
      should now include `### Переписка с клиентом` (verifiable via
      `enrichment_runs.prompt_tokens` going up vs prior runs, or
      logged at debug)

---

## Files changed (cumulative)

```
apps/api/alembic/versions/20260507_0008_channel_connections.py             (new, 72)
apps/api/alembic/versions/20260507_0009_inbox_items_and_activity_email.py  (new, 127)
apps/api/alembic/env.py                                                    (+1)
apps/api/app/activity/models.py                                            (+8)
apps/api/app/activity/schemas.py                                           (+6)
apps/api/app/config.py                                                     (+16)
apps/api/app/enrichment/orchestrator.py                                    (+57)
apps/api/app/inbox/email_parser.py                                         (new, 155)
apps/api/app/inbox/gmail_client.py                                         (new, 224)
apps/api/app/inbox/matcher.py                                              (new, 131)
apps/api/app/inbox/models.py                                               (new, 121)
apps/api/app/inbox/oauth.py                                                (new, 131)
apps/api/app/inbox/processor.py                                            (new, 196)
apps/api/app/inbox/routers.py                                              (new, 232)
apps/api/app/inbox/schemas.py                                              (new, 45)
apps/api/app/inbox/services.py                                             (new, 278)
apps/api/app/inbox/sync.py                                                 (new, 255)
apps/api/app/main.py                                                       (+3)
apps/api/app/scheduled/celery_app.py                                       (+5)
apps/api/app/scheduled/jobs.py                                             (+169)
apps/api/pyproject.toml                                                    (+3)
apps/api/tests/test_inbox_matcher.py                                       (new, 413)
apps/api/tests/test_email_context_in_brief.py                              (new, 227)
apps/api/tests/test_inbox_services.py                                      (new, ~340)
apps/web/app/(app)/inbox/page.tsx                                          (new, 479)
apps/web/components/layout/AppShell.tsx                                    (+30/-3)
apps/web/components/lead-card/ActivityTab.tsx                              (+72/-1)
apps/web/lib/hooks/use-inbox.ts                                            (new, 66)
apps/web/lib/types.ts                                                      (+52)
docs/brain/03_DECISIONS.md                                                 (+24)
docs/brain/00_CURRENT_STATE.md                                             (Sprint 2.0 section)
docs/brain/02_ROADMAP.md                                                   (Sprint 2.0 → DONE)
docs/brain/04_NEXT_SPRINT.md                                               (rewritten for 2.1)
docs/brain/sprint_reports/SPRINT_2_0_GMAIL_INBOX.md                        (new — this file)
infra/production/.env.example                                              (+16)
```

Net: ~3 600 lines added across 31 files (24 new, 7 modified).

---

## Next sprint pointer

→ `docs/brain/04_NEXT_SPRINT.md` — **Sprint 2.1 Bulk Import / Export**.

Decision context for skipping the rest of the original Sprint 2.0 scope
(Quote builder, WebForms, Knowledge Base CRUD UI, Telegram Business): the
Gmail loop is rich enough on its own to be worth sprinting separately,
and Bulk Import/Export is an unblocking item for the team's data-entry
pain right now (existing leads in Bitrix24 / Excel).

The deferred items stay on the Phase 2 envelope — see `02_ROADMAP.md`.
