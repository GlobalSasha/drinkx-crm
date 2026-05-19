# Sprint 3.7 — Email Workflow Simplification

**Status:** 📋 SPEC (pre-implementation)
**Date:** 2026-05-19
**Branch:** `sprint/3.7-email-workflow` (to create off main)
**Tracking:** `docs/brain/04_NEXT_SPRINT.md` (will replace after spec approval)

---

## Goal

Strip the `/inbox` manual-triage UI and the AI-classifier-as-suggestion
pattern. Replace with a **multi-gate prefilter** that drops bulk mail before
any LLM, and an **auto-create-with-review** path for genuinely new B2B
prospects. Manager workflow centers on Lead Card and Pool — no separate
inbox-zero surface to maintain.

This sprint codifies the design discussion on 2026-05-19 after the user
clarified the original intent: email integration is meant to **enrich
existing leads with conversation context**, not to be a parallel inbox client.

## What we are NOT building

(Explicit out-of-scope so the implementer doesn't pull in adjacent ideas.)

- **Gmail send from Lead Card.** Deferred. Managers reply via Gmail
  natively; threading via `In-Reply-To` header brings replies back into
  the lead's Activity automatically.
- **Mailbox-as-deal-source rules** (amoCRM pattern: «emails to this
  address → create deals on stage X»). Confidence threshold replaces
  rule engine.
- **Multi-mailbox per manager.** One Gmail OAuth per manager stays.
- **Email parser / forms-by-email.** `/forms` with the public POST
  endpoint (Sprint 3.6) already covers form submissions. Email-forward
  forms would duplicate that surface.
- **Feedback loop for AI confidence learning.** Future enhancement
  if/when we have enough «не лид» labels to retrain anything.

## Already shipped (do NOT rebuild)

Sprint 3.4 + Sprint 3.6 hotfixes shipped most of the substrate:

- `Lead.source` carries `"form:<slug>"` for landing leads; we extend
  with `"auto_email"` for AI-created ones.
- `route_email` in `apps/api/app/inbox/processor.py` already routes to
  `attach_to_lead` for `known_company` / `known_contact` matches — this
  is the no-LLM Layer 1 the user asked about.
- `route_email` already filters bulk mail via:
  - `noreply@` prefix list
  - `noreply` / `no-reply` substring in local-part (hotfix PR #50)
  - `List-Unsubscribe` / `List-Unsubscribe-Post` headers (PR #50)
  - `Precedence: bulk | list | junk` (PR #50)
  - `Auto-Submitted` ≠ `no` (PR #50)
  - `unsubscribe` / `отписаться` / `рассылка` body keywords
  - Personal-mailbox (gmail.com, yandex.ru, …) without B2B keyword
- `Activity.type=email` rows render in Lead Card «Активность» + «Переписка»
  tabs (Sprint 3.4).
- `InboxItem` model + `/inbox` page exist as the surface we are dismantling.

---

## Design — three layers + safety net

### Layer 1 — Auto-attach (no LLM)

Already works. This sprint **disables** the optional AI-comment hook so
Layer 1 truly costs zero tokens by default:

- `_enqueue_lead_agent_refresh` in `app/inbox/message_services.py` and
  the matching path inside `processor.py` gated behind a new workspace
  setting `auto_lead_agent_refresh_on_inbound` (default `false`).
- When `false`: matched inbound writes the Activity row and stops there.
  No Чак comment, no token spend.
- When `true`: existing behavior preserved (admin can opt back in via
  Settings → AI → «AI комментирует входящие»).

### Layer 2 — Multi-gate filter for unmatched mail

Already-existing filters become **Gates 1 and 2**. We add **Gate 3** and
**Gate 4** to drop more before LLM and to harden the decision.

**Gate 1 — RFC bulk-mail headers** (already shipped PR #50)
- `List-Unsubscribe` / `List-Unsubscribe-Post` → ignore
- `Precedence: bulk|list|junk` → ignore
- `Auto-Submitted ≠ no` → ignore
- `noreply` / `no-reply` substring in local-part → ignore

**Gate 2 — Personal mailbox without B2B keyword** (already shipped)
- Sender domain ∈ `{gmail, yandex, mail.ru, bk.ru, list.ru, …}` AND
  body does not contain any of `{drinkx, кофе-станция, автомат,
  концентрат, пилот, прайс, ...}` → ignore.

**Gate 3 — Service local-parts from unknown domains** (NEW)
- Add a new tuple `_SERVICE_LOCAL_PARTS` in `processor.py`:
  ```python
  _SERVICE_LOCAL_PARTS = (
      "info", "support", "hello", "hi", "team",
      "marketing", "news", "newsletter", "contact",
      "press", "media", "events", "webinar", "academy",
      "billing", "invoice", "accounts", "finance",
  )
  ```
- If `local_part(sender) in _SERVICE_LOCAL_PARTS` AND `has_known_contact == False`
  AND `has_known_company == False` → `RoutingDecision("ignore", "service_local_part")`.
- Known-contact override stays — `info@known-customer.ru` from a tracked
  client still auto-attaches via Gate 0 priority.

**Gate 4 — AI classifier, threshold 0.85** (CHANGE)
- Reach Gate 4 only after Gates 1–3 pass.
- Same prompt as today (`_INBOX_SUGGESTION_SYSTEM` in `app/scheduled/jobs.py`)
  but tighter threshold and **auto-act**, not suggest:
  - `confidence ≥ 0.85` AND `action == "create_lead"` → fire auto-create
    flow (Layer 2 output, see below).
  - `confidence ≥ 0.85` AND `action == "add_contact"` → add Contact to
    matched company (we'd need company match — usually rare for unmatched).
  - `confidence < 0.85` OR `action == "ignore"` → silent drop.
- No `/inbox` row written. No manual triage.

### Auto-create output (Gate 4 success path)

For `confidence ≥ 0.85 AND action == "create_lead"`:

1. Resolve domain → `Company` row (create if not exists).
2. Create `Contact` from `From:` name + email.
3. Create `Lead`:
   - `workspace_id` = the manager's workspace (from the Gmail channel).
   - `company_id` = the Company.
   - `primary_contact_id` = the Contact.
   - `assignment_status = "pool"` (lands in `/leads-pool`).
   - `source = "auto_email"`.
   - `needs_review = TRUE` (new column, see Layer 3 safety net).
   - `assigned_to = NULL`.
4. Write `Activity` row of type `email` with the message contents.
5. Optional: emit a structured log line for ops monitoring of
   auto-create rate.

### Layer 3 — `needs_review` safety net

A boolean column on `Lead` so the manager can quickly confirm or
delete AI-created leads without a separate triage screen.

**Schema:**
- `leads.needs_review BOOLEAN NOT NULL DEFAULT FALSE`
- Set `TRUE` only by Gate 4 auto-create. Manager toggles to `FALSE` on
  confirmation. Any manual lead creation (form submission, manager
  «+ Лид», CSV import) sets `FALSE`.

**UI** — `/leads-pool` only:
- Per-row pill «⚠️ AI создал · 87%» next to the existing source chip on
  rows where `needs_review = TRUE`.
- Two extra buttons on the row: «Подтвердить» (sets needs_review =
  FALSE, no other state change) and «Не лид» (soft-delete via
  `assignment_status = "deleted"` + `archived_at = NOW()`).
- The «Подтвердить» click can stay inline; the «Не лид» click is
  destructive enough to need the existing confirm modal.

Confidence percentage stamp lives on the Activity row's
`payload_json.confidence` (already present from the AI classifier
output). The pool UI reads it from the Activity, or — simpler — from
`Lead.ai_data["auto_create_confidence"]` set at creation time.

### What we tear out

The `/inbox` page becomes obsolete the moment Gate 4 stops writing
`InboxItem` rows.

- `apps/web/app/(app)/inbox/page.tsx` — DELETE.
- Sidebar nav entry «Входящие» in `SidebarNavContainer.tsx` — REMOVE.
- `apps/web/components/inbox/UnmatchedMessagesSection.tsx` — DELETE.
- `apps/api/app/inbox/services.py` — the confirm / dismiss endpoints
  for InboxItem stay live (data still exists), but routers stop being
  registered (or stay only for admin debug). DELETE if not used by
  anything else.
- `apps/api/app/inbox/models.py::InboxItem` — DO NOT drop the table.
  Historical rows have audit value; the model itself stays for the
  `/api/inbox/unmatched/messages` endpoint that the unmatched messengers
  section still uses (Telegram/MAX/Phone unmatched messages — different
  domain, not Gmail). Confirm by reading
  `apps/web/components/inbox/UnmatchedMessagesSection.tsx` before
  deletion. If it covers only Gmail unmatched, full removal is safe.

The `_run_inbox_suggestion` job logic moves to a new
`_run_auto_create_or_ignore` job that performs the auto-create when
confidence is high, drops the message when not. Same prompt, different
action handler.

---

## Gates

### G1 — Layer 1 token off-switch

- [ ] Add workspace setting `auto_lead_agent_refresh_on_inbound: bool
      DEFAULT false`.
- [ ] Gate `_enqueue_lead_agent_refresh(...)` in
      `app/inbox/message_services.py` behind it.
- [ ] Same gate in `app/inbox/processor.py` if it has a parallel call.
- [ ] Settings UI toggle under Settings → AI («AI комментирует входящие»).
- [ ] Default: OFF for all existing workspaces. Migration sets default;
      no user data change.

### G2 — Service local-parts (Gate 3 of the filter)

- [ ] Add `_SERVICE_LOCAL_PARTS` constant + branch in `route_email`.
- [ ] Branch fires BEFORE `has_known_company` / `has_known_contact`
      check — except: if either is true, override and attach.
- [ ] Unit tests: `info@unknown.com` ignored, `info@known-customer.ru`
      attaches.

### G3 — Auto-create flow

- [ ] Migration `leads.needs_review BOOLEAN NOT NULL DEFAULT FALSE`.
- [ ] Update `LeadOut` Pydantic + frontend `LeadOut` interface with
      `needs_review: boolean`.
- [ ] Replace Celery task `generate_inbox_suggestion(inbox_item_id)` with
      `auto_create_lead_from_email(workspace_id, channel_id, from_email,
      subject, body_preview, raw_payload)`. Task args carry the email
      payload directly — no `InboxItem` row is written before invocation.
      The async core (`_run_auto_create_or_ignore`) does all DB work
      conditionally on the AI verdict: on `confidence >= 0.85 AND
      action == "create_lead"` it materialises Company / Contact / Lead
      / Activity in one transaction; otherwise it returns without writing.
- [ ] Caller in `processor.py` (the branch that previously created an
      `InboxItem` and enqueued `generate_inbox_suggestion`) now just
      enqueues the new task with the payload args and skips the
      `InboxItem` create.
- [ ] Confidence cutoff bumped from current (any) to `>= 0.85`. Below
      threshold = silent drop (no row written anywhere).
- [ ] Resolve / create `Company` by sender domain; resolve / create
      `Contact` by sender email.
- [ ] Write `Activity` row of type `email` on the new lead with subject
      + body preview + UTM=none + `payload_json.confidence`.
- [ ] Stamp `lead.ai_data["auto_create_confidence"]` for pool UI access.

### G4 — `needs_review` UI on /leads-pool

- [ ] Backend: `?needs_review=true` filter on `GET /leads/pool`
      (mirror Sprint 3.6 G2 `form_id` filter pattern).
- [ ] Frontend: per-row pill «⚠️ AI создал · 87%» when
      `lead.needs_review` is true (read confidence from
      `lead.ai_data.auto_create_confidence`).
- [ ] Two new buttons in the row tray («Подтвердить», «Не лид»). Inline
      handlers:
  - «Подтвердить» → `PATCH /leads/{id}` with `{needs_review: false}`.
  - «Не лид» → existing Modal confirmation → `PATCH /leads/{id}`
    with `{assignment_status: "deleted", archived_at: now()}`.
- [ ] Filter chip in the existing pool filter bar: «Только AI-созданные».

### G5 — Tear out `/inbox` (Gmail triage page)

- [ ] Delete `apps/web/app/(app)/inbox/page.tsx`.
- [ ] Remove «Входящие» sidebar nav entry in `SidebarNavContainer.tsx`.
      Verify the badge plumbing (`useInboxCount`) doesn't break anything
      else; remove if dead.
- [ ] Decide on `UnmatchedMessagesSection.tsx`: read it; if it ONLY
      surfaces Gmail unmatched items, delete. If it serves Telegram /
      Phone unmatched too (which is its Sprint 3.4 role), KEEP and
      relocate to `/today` or a small admin surface.
- [ ] Audit backend routers: any endpoint that exists solely to serve
      the deleted UI gets removed (`POST /api/inbox/items/{id}/confirm`,
      `POST /api/inbox/items/{id}/dismiss`, the Gmail `/inbox/pending`
      list endpoint that powered the deleted page). The new
      `auto_create_lead_from_email` Celery task is the only inbound
      LLM entry-point that remains.

### G6 — Manager-facing documentation

- [ ] Update `docs/landings.md` (or create `docs/email-workflow.md`)
      explaining the new flow:
  - Подключить Gmail → CRM мониторит входящие.
  - Письма от уже-известных клиентов автоматически попадают в
    «Активность» лида.
  - Письма с новых B2B-адресов с высоким confidence создают лид в
    Pool с пометкой ⚠️.
  - Менеджер раз в день в Pool подтверждает / отклоняет AI-лидов.
  - Остальное (рассылки, billing, личное) тихо игнорируется.

---

## Pre-PR gates per checkbox

Per `CLAUDE.md`:
- Backend: `python -m pytest --collect-only` (or `.venv/bin/pytest`) +
  targeted tests for `route_email` Gate 3 and `auto_create_lead_from_email`.
- Frontend: `npm run typecheck` + `npm run lint` + `pnpm build`.

Commit messages reference the gate: `feat(inbox): G3 — auto-create lead
with needs_review safety net`.

---

## Token cost projection

Before (today's `/inbox` AI suggestion on every unmatched email):
- Per email: ~$0.0003 (MiMo Flash, 550 in + 40 out)
- 1000 unmatched/month: ~$0.30

After (Gates 1–3 drop ~80% of unmatched before LLM):
- ~200 reach Gate 4 per month
- Per email: same $0.0003
- 1000 input emails: **~$0.06/month** (≈5 ₽)

This is rounding error in the API budget. The real wins are **manager
attention** (no /inbox to maintain) and **product simplicity** (one less
page, one less mental model).

---

## Smoke checklist (post-merge)

1. **Send a real inbound to a known contact email** → should auto-attach
   to lead's Activity. Confirm via `/leads/{id}?tab=activity`.
2. **Send from an unknown gmail.com personal account without keywords**
   → should be silently ignored (Gate 2). Confirm by tail-ing API
   logs for `personal_no_keyword`.
3. **Send from `info@some-unknown-corp.ru`** with a coffee-related
   subject → should be ignored (Gate 3). Log: `service_local_part`.
4. **Send from `alex@coffee-roastery-zarya.ru`** with «Заинтересованы
   в коммерческом предложении DrinkX» → should reach Gate 4 with
   confidence ≥ 0.85, create a Lead in Pool with `needs_review=true`.
   Confirm pill is visible in `/leads-pool`.
5. **Click «Подтвердить» on that lead** → pill disappears, lead becomes
   a normal pool lead.
6. **`/inbox` URL** → either returns 404 or redirects (depending on
   final decision on route removal).
7. **Sidebar** → no «Входящие» entry visible.
8. **Settings → AI → «AI комментирует входящие»** → toggle is OFF by
   default; flipping it ON makes the next matched inbound trigger a
   Чак comment in the lead's feed.

---

## Open questions

None outstanding. Decisions resolved during the design discussion on
2026-05-19:

- Layer 1 stays no-LLM by default. AI comments on inbound are opt-in.
- Confidence threshold raised from a soft suggestion (any) to a hard
  0.85 cutoff with auto-create.
- `needs_review` pill in Pool replaces the deleted `/inbox` triage page.
- Gmail send out of scope this sprint.
