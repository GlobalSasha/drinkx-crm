# Next sprint — TBD

Sprint 3.4 (Unified Inbox: Telegram + Mango + STT) closed on 2026-05-12.
See `docs/brain/sprint_reports/SPRINT_3_4_UNIFIED_INBOX.md` for the report,
scope, carry-overs, ENV vars, and smoke checklist.

---

## Pick from one of:

### Sprint 3.5 — Inbox follow-ups (recommended, ~3–4 days)

Direct carry-overs from 3.4. The lift is small because the abstraction
landed in 3.4 — every item below is "drop the adapter + wire the seam":

- **MAX Bot (G3 from 3.4 spec)** — `app/inbox/adapters/max_messenger.py`
  mirroring `TelegramAdapter`; `POST /api/webhooks/max`; composer chip in
  `InboxTab.tsx`.
- **Gmail send (G5 from 3.4 spec)** — request `gmail.send` scope on
  first connect; existing connections get an inline «переподключить»
  hint; `POST /leads/{id}/inbox/send` for `channel='email'` routes
  through `gmail_client.send_message`.
- **Per-manager Telegram bots** — store tokens per
  `(workspace_id, user_id)` in `channel_connections` (mirror Gmail
  OAuth path); webhook URL becomes `/api/webhooks/telegram/{connection_id}`;
  `DEFAULT_WORKSPACE_ID` retires. TODO already captured in
  `app/inbox/adapters/telegram.py` + `app/inbox/webhooks.py`.

### Sprint 3.2 — Lead AI Agent polish (~3–5 days)

Parked since the 3.1 close. Per-suggestion id + persistent dismiss;
thumbs up/down; chat streaming via SSE; LLM-based SPIN analysis of
inbound. Full scope in `docs/brain/02_ROADMAP.md` under «Sprint 3.2
— Lead AI Agent polish».

### Soft-launch hardening

- Sentry DSNs (init wiring is ready since 2.7)
- `pg_dump` cron install on host
- End-to-end smoke ritual after each deploy (post-2026-05-08 tech-debt #9)

---

When you pick one, replace this file with the chosen spec and start
ticking gate checkboxes the same way 3.4 was tracked.
