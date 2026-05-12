# Sprint 3.4 — Unified Inbox: Telegram + Mango + транскрипция

**Status:** ✅ DONE (MVP variant B — 6-day scope)
**Date:** 2026-05-11 → 2026-05-12
**Scope chosen:** B (Telegram + Mango + SaluteSpeech transcription, no MAX, no Gmail send)

---

## 1. What shipped

### Backend

| Layer | Component | Commit |
|---|---|---|
| Schema | `inbox_messages` (migration 0025) + `leads.tg_chat_id` / `leads.max_user_id` (migration 0026) | `0729177` |
| Adapter Protocol | `app/inbox/adapters/base.py` — `ChannelAdapter` | `0729177` |
| Service layer | `app/inbox/message_services.py` — `normalize_phone`, `match_lead`, `receive`, `send`, `place_call`, `list_for_lead`, `list_unmatched_messages`, `assign`, `_enqueue_lead_agent_refresh`, `_enqueue_transcribe` | `0729177` + `c33a9da` + `4aff0fb` |
| Telegram | `app/inbox/adapters/telegram.py` — parse_webhook (`message` + `business_message`), send via Bot API; `POST /api/webhooks/telegram` with `X-Telegram-Bot-Api-Secret-Token` constant-time check | `c33a9da` |
| Mango Office | `app/inbox/adapters/phone.py` — parse `call_end`/`missed_call`, click-to-call with HMAC `sign`; `POST /api/webhooks/phone` (form + sign over `json` field); `POST /leads/{id}/inbox/call` (no DB write — canonical row arrives via webhook) | `4aff0fb` |
| STT + summary | `app/inbox/stt/` (base / salute / whisper / factory); `transcribe_call_async` orchestrator: download → STT → MiMo Flash summary → persist transcript+summary+provider → rewrite Activity body → 60s Lead-Agent kick | `6aca226` |
| Tasks | `transcribe_call` Celery task registered in `app/scheduled/jobs.py` (sync wrapper, async core in `app/inbox/message_tasks.py`) | `4aff0fb` + `6aca226` |
| Routes | `GET /leads/{id}/inbox` (merged feed), `POST /leads/{id}/inbox/send`, `POST /leads/{id}/inbox/call`, `GET /api/inbox/unmatched/messages`, `PATCH /api/inbox/messages/{id}/assign`, `POST /api/webhooks/{telegram,phone}` | various |

### Frontend

| Layer | Component | Commit |
|---|---|---|
| Types | `InboxFeedEntry/Out`, `InboxMessageOut`, `InboxSendIn`, `InboxCallIn/Out`, `InboxFeedChannelLink` | `9a3722d` |
| Hooks | `useLeadInbox` (10s polling), `useLeadInboxSend`, `useLeadInboxCall`, `useInboxUnmatchedMessages` (15s polling), `useAssignInboxMessage` | `9a3722d` + `3359ad7` |
| Lead card | 4-й таб «Переписка» (`InboxTab.tsx`): filter [Все/Gmail/Telegram/Телефон], lente с channel badges + direction labels, collapsible транскрипт, composer (Telegram), кнопка «Позвонить» (localStorage-кеш extension) | `9a3722d` |
| /inbox | Секция «Мессенджеры и звонки» под существующим email-списком, inline LeadSearchPicker → assign | `3359ad7` |

### Tests

44 mock unit tests, все зелёные:

| File | Tests | Coverage |
|---|---|---|
| `test_inbox_messages.py` | 10 | `normalize_phone` (7 cases), `match_lead` by tg_chat_id, `receive` dedup, `receive` unmatched |
| `test_inbox_telegram.py` | 11 | parse direct/business/no-text, send happy/no-token/bad-status, send service happy/no-recipient/wraps-errors, receive matched (Activity + agent kick) / unmatched |
| `test_inbox_phone.py` | 14 | parse answered/missed/outbound/inferred, `compute_sign` formula, initiate happy/no-config/bad-status, place_call happy/no-phone/wraps-errors, transcribe dispatch yes/no on answered+media/missed/answered-no-media |
| `test_inbox_transcribe.py` | 9 | factory default + fallback, salute token caching + oauth-fail + silent + no-creds, orchestrator happy / missed-skip / STT-failure-persists-provider |

Full sweep: **393 passed**, **22 pre-existing failures** unchanged (all unrelated to 3.4 — Postgres-unavailable env, ancient test_inbox_matcher regression on main pre-3.4).

---

## 2. Carry-overs (NOT in this sprint)

| Item | Where it goes |
|---|---|
| MAX Bot (G3) | Original spec preserved; pick up when MAX is a priority |
| Gmail send (G5) | Spec preserved; requires `gmail.send` scope migration |
| Per-manager Telegram bots | TODO captured in `app/inbox/adapters/telegram.py` + `app/inbox/webhooks.py`. Migration path: store token+secret per `(workspace_id, user_id)` in `channel_connections` (like Gmail), webhook URL becomes `/api/webhooks/telegram/{connection_id}`, `DEFAULT_WORKSPACE_ID` retires |
| `test_inbox_matcher::test_processor_creates_activity_on_high_confidence_match` | Pre-existing regression on main pre-3.4. Sidecar fix tracked separately |
| Email leg of `GET /leads/{id}/inbox` | Currently empty (placeholder until G5). Email shows on the existing Activity tab |
| MAX / Email chips in InboxTab composer | UI hints already display "Email/MAX позже" so the spot is reserved |

---

## 3. ENV variables to provision (production)

Add to `/opt/drinkx-crm/.env` BEFORE the smoke checklist below:

```env
# Telegram (G2)
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=

# Workspace anchor for single-tenant webhook routing (G2 + G4)
DEFAULT_WORKSPACE_ID=

# Mango Office VPBX (G4)
MANGO_API_KEY=
MANGO_API_SALT=
# MANGO_API_BASE defaults to https://app.mango-office.ru — override only for sandbox

# SaluteSpeech (G4b)
STT_PROVIDER=salute
SALUTE_CLIENT_ID=
SALUTE_CLIENT_SECRET=
# SALUTE_SCOPE defaults to SALUTE_SPEECH_PERS
```

---

## 4. Smoke checklist (operator-side, after creds land)

### One-time webhook registration

```bash
# Telegram
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d url="https://crm.drinkx.tech/api/webhooks/telegram" \
  -d secret_token="${TELEGRAM_WEBHOOK_SECRET}"

# Mango Office → personal cabinet → Integrations → Webhooks
#   URL: https://crm.drinkx.tech/api/webhooks/phone
#   Events: call_end, missed_call
```

### Smoke

1. **Telegram inbound matched** — DM the bot from a phone whose number matches an existing `leads.phone`. Expect: row in `inbox_messages` with `lead_id` set, Activity in the lead card, Lead-Agent banner refreshes within ~15 min.
2. **Telegram inbound unmatched** — DM from an unknown number. Expect: row with `lead_id IS NULL`, visible in `/inbox` under "Мессенджеры и звонки".
3. **Telegram outbound** — open lead card → tab «Переписка» → composer → "Отправить". Expect: 200, message arrives in the client's Telegram, outbound row in feed.
4. **Mango incoming answered call with recording** — call the manager extension from the lead's phone. Expect: `inbox_messages` row with `call_status='answered'`, recording link in the feed, transcribe Celery task fires 30s later, transcript+summary appear on the row within ~1 min.
5. **Mango missed call** — let it ring out. Expect: `call_status='missed'`, no transcription kicked.
6. **Click-to-call** — open lead card → «Позвонить» → enter extension. Expect: 200 dialing, manager's phone rings, after the call the `call_end` event creates the canonical row.
7. **Assign unmatched** — `/inbox` → find an unmatched messenger row → "Привязать к лиду" → pick lead. Expect: row vanishes from unmatched, appears in the lead card feed.

---

## 5. Files

```
apps/api/
  alembic/versions/
    20260511_0025_inbox_messages.py
    20260511_0026_leads_messenger_ids.py
  app/inbox/
    adapters/{base,telegram,phone}.py
    stt/{base,salute,whisper,factory}.py
    webhooks.py
    message_services.py            (extended)
    message_tasks.py               (new — transcribe_call_async)
    models.py / schemas.py / routers.py  (extended)
  app/scheduled/jobs.py            (+transcribe_call wrapper)
  app/config.py                    (+9 settings)
  tests/
    test_inbox_messages.py
    test_inbox_telegram.py
    test_inbox_phone.py
    test_inbox_transcribe.py

apps/web/
  components/inbox/UnmatchedMessagesSection.tsx
  components/lead-card/{InboxTab.tsx, LeadCard.tsx}
  lib/hooks/{use-lead-inbox.ts, use-inbox.ts}
  lib/types.ts                     (+inbox channel types)
  app/(app)/inbox/page.tsx
```

---

## 6. Commits

| Commit | Gate |
|---|---|
| `e379f33` | chore: archive AUTOPILOT, point CLAUDE.md to brain files, add Sprint 3.4 spec |
| `0729177` | G1 — schema + skeleton |
| `c33a9da` | G2 — Telegram |
| `4aff0fb` | G4 — Mango |
| `6aca226` | G4b — STT + summary |
| `9a3722d` | G6 — InboxTab UI |
| `3359ad7` | G7 — unmatched section |
| (G8)    | this report |
