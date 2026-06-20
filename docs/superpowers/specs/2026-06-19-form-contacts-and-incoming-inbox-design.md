# Form-lead contacts + richer "Входящие" inbox

**Date:** 2026-06-19
**Type:** Feature (backend extraction + Contact creation, inbox read-model + UI)

## Problem

A web-form submission (`заявка`) creates a Lead with `email`/`phone` written onto
the **Lead** itself, but **no `Contact` row**. Consequences:

1. The lead card's **«Контакты»** tab is empty for every form lead, so the
   clickable `mailto:`/`tel:` actions (which only render there) never appear, and
   there is no primary ЛПР.
2. The **«Входящие»** inbox (`/incoming`, read-model over `FormSubmission`) shows
   the visitor's data poorly: the actual message is buried in a dump of every
   field on one line, phone/email are plain text (not clickable), and the source
   (channel + domain) is not clearly surfaced. The visitor's name is lost — it
   lives inside the message blob, never mapped to a field.

The drinkx.ru landing posts a single message-style field whose value is a
human-readable summary of all fields (`Имя: … Сегмент: … Сообщение: … Источник:
…`), plus separate `email`/`phone` fields. So both the visitor name and the real
question are embedded in a `Label: value` block, not clean keys.

Bug found while investigating: `extract_snippet` matches lowercase keys
(`сообщение`) but forms post `Сообщение`, so for some forms the snippet is
silently empty.

## Decisions

- **Auto-create a `Contact`** from the submission when the lead has an `email`
  **or** `phone`. Link it to the lead and set it as **primary ЛПР**
  (`lead.primary_contact_id`) when the lead has none yet.
- Contact provenance: `source="webform"`, `confidence="high"`,
  `verified_status="verified"` — the visitor self-reported it, so we do **not**
  raise the "AI · нужна проверка" banner.
- The contact **name** field is required (non-null), so it has a fallback chain
  (below). The existing `name → company_name` form-field mapping is **left
  untouched** to avoid regressions; person-name keys are a separate set that
  excludes bare `name`.
- **Question extraction is done CRM-side** by parsing the message blob. We do not
  change the drinkx.ru site. A clean dedicated field, if a form ever sends one,
  takes priority over blob parsing.
- "Catch contacts from any field" (non-standard contact fields like «Способ
  связи») is **out of scope** — the email/phone mapping in `_project_payload`
  is unchanged.

## Phase 0 findings (verified 2026-06-19, live data)

Inspected the real Осипов submission, the `/incoming` rows, our embed
(`embed.py`), and the form configs in `/forms`:

- **Form config ≠ actual payload.** The "Сайт drinkx.ru" form is configured
  with 3 fields (company name, email, phone), but real submissions carry
  Имя / Сегмент / Интересует модель / Сообщение / Источник. The live site is a
  **custom integration** POSTing its own payload straight to `/submit`; it
  ignores our embed and the CRM field config. So we cannot trust configured
  field keys for these forms.
- **The `Label: value` blob is the PRIMARY path**, not a fallback. All four
  drinkx forms POST a newline-separated blob into a lowercase `message`/`comment`
  field (that is why `extract_snippet` matched at all). Our embed's clean
  per-field keys are the secondary path (future / embed-built forms).
- **Per-form data differs:**
  - *Сайт drinkx.ru*: clean `email` + `phone` + a `name→company` field, plus the
    blob. The person's name lives in the blob under `Имя:`, distinct from the
    company. → Contact is created; name parsed from the blob.
  - *Лендинг станция/бар/меню*: blob with Способ связи / Формат заведения,
    **no email/phone, no free-text question.** → no Contact (nothing to create),
    and the question block must hide gracefully.

Implications folded into the design below: blob parsing is primary; the inbox
question block degrades gracefully when there is no message; Contact creation
realistically fires only for submissions that carry email/phone.

## Shared extraction helpers (`apps/api/app/forms/lead_factory.py`)

Both Contact creation and the inbox read-model need to read fuzzy keys and parse
the blob, so the helpers live in `lead_factory.py` and are imported by `inbox.py`.

1. `_lookup(payload, keys)` — case-insensitive, normalized (`_normalize_key`
   already exists) lookup over payload keys; returns first non-empty value.
2. `_parse_labeled_block(text) -> dict[str, str]` — split a `Label: value` blob
   (newline-separated) into a normalized-label → value dict. Returns `{}` for
   non-blob text.
3. `extract_person_name(payload) -> str | None`
   - `_lookup` over `PERSON_NAME_KEYS = {имя, фио, ф.и.о., контактное лицо,
     ваше имя, как вас зовут, contact name, contact_name}` (note: **not** bare
     `name`).
   - else parse the message blob and read its `имя/фио/контакт/name` label.
   - else `None`.
4. `extract_question(payload, *, limit=200) -> str | None` — replaces
   `extract_snippet`. Returns the visitor's **free-text message**, or `None`
   when there is none (e.g. landing forms with only structured fields):
   - `_lookup` over `QUESTION_KEYS = {вопрос, question, сообщение, message,
     комментарий, comment, comments}` (priority order).
   - If the value is a `Label: value` blob, return the value of its
     `сообщение/вопрос/message/comment` label when present; else, since a blob
     with no message line is just structured fields, return `None`.
   - Trim to `limit`; empty → `None`.
5. `extract_summary(payload, *, limit=200) -> str` — a one-line recap used when
   there is no free-text question. Parses the blob and joins its remaining
   fields as `Label — value · Label — value`, excluding contact fields and noise
   (`Источник`, `email`, `phone`, name/company). For the landing example →
   `Способ связи — test · Формат заведения — Клуб`. Empty when no blob.

This fixes the case-sensitivity bug for free (normalized lookup) and works
whether the form sends clean fields or the current blob.

## Feature A — Contact creation

In `create_lead_from_submission`, after `await session.flush()` (lead has an id)
and the email/phone copy:

```
if lead.email or lead.phone:
    name = extract_person_name(payload) or lead.email or lead.phone or "Контакт с формы"
    contact = Contact(
        workspace_id=lead.workspace_id, lead_id=lead.id,
        name=name[:120], email=lead.email, phone=lead.phone,
        source="webform", confidence="high", verified_status="verified",
    )
    session.add(contact)
    await session.flush()
    if lead.primary_contact_id is None:
        lead.primary_contact_id = contact.id
```

- `Contact` validators normalize `email_normalized`/`phone_e164` on assignment.
- Runs exactly once per submission → no duplicate-contact risk.
- Caller already commits; no transaction change.

## Feature B — "Входящие" inbox

### Backend — `apps/api/app/forms/inbox.py` + `schemas.py`

- `list_inbox` item dict: replace `snippet` with `question` (via
  `extract_question`) and `summary` (via `extract_summary`), and add
  `contact_name` (via `extract_person_name`). `source_domain` is already in the
  dict.
- `InboxItemOut`: add `contact_name: str | None`, `question: str | None`,
  `summary: str`; ensure `source_domain: str | None` is present. Drop `snippet`.
- `extract_snippet` is replaced by `extract_question`/`extract_summary`; update
  the `__all__` export and the `list_inbox` caller (`count_new` does not use it).

### Frontend — `apps/web/app/(app)/incoming/page.tsx` + `lib/types.ts`

`InboxItemOut` type: add `contact_name`, `question`, `summary`; drop `snippet`.
The `Row` component is restructured:

- **Кто**: `contact_name` (when present) + `company_name`.
- **Контакты (clickable)**: phone as a `tel:` chip ("Позвонить") and email as a
  `mailto:` chip ("Написать"), each with a small **copy** button. Reuse the
  chip/`LinkBtn` pattern from `ContactsTab.tsx`. `e.stopPropagation()` so the
  chip click does not also trigger the row's "open lead" navigation.
- **Источник**: existing channel chip **+** `source_domain` rendered as text.
- **Вопрос**: when `question` is set, a labelled block ("Вопрос клиента")
  showing it, `line-clamp-2`. When `question` is null but `summary` is set
  (structured-only landing forms), show `summary` under a neutral "Из заявки"
  label instead. When both are empty, render nothing. Replaces the all-fields
  blob.

Row click still navigates to `/leads/{lead_id}`; the "Открыть лида →" affordance
stays.

## Out of scope (YAGNI)

- Expanding email/phone field mapping ("catch contacts everywhere").
- Any change to the drinkx.ru website / embed.
- Replying or bulk actions from the inbox — view + quick call/write only.
- Backfilling Contacts for historical form leads (new submissions only).
- The lead-card activity comment keeps showing the raw blob as-is (we only clean
  the inbox read-model, not the stored comment).
- De-duplicating Contacts from repeat submissions of the same person — repeat
  submissions already create separate leads; merging stays manual via the
  existing DuplicatesModal.

## Testing

**Backend (pytest):**
- `extract_person_name`: clean `имя` key; only in blob (`Имя: …`); absent → None.
- `extract_question`: clean field; blob with `Сообщение:` line; capitalized key
  (`Сообщение`) regression; structured-only blob (no message line) → None.
- `extract_summary`: structured blob → `Label — value · …` excluding noise;
  no blob → "".
- `create_lead_from_submission`: email+phone → Contact created and set as primary
  ЛПР; neither (landing case) → no Contact; existing `primary_contact_id` is not
  overwritten.

**Frontend / manual on `/incoming`:** the Осипов заявка shows contacts as
clickable chips, the question «какую проблему решает дринкс?» as its own block,
and the source (WEBSITE + domain).

## Assumptions & verification

- Phase 0 (above) verified the blob shape and the config-vs-payload gap from live
  data. What is **not** byte-confirmed: the exact key the blob sits under
  (`message` vs `comment` vs lowercase `сообщение`) and the exact blob labels for
  the landing forms. Extraction is **key-set / label-set based**, so any of those
  keys is covered; the first implementation step still logs one real
  `raw_payload` (temporary, removed before commit) to confirm the label spellings
  for `extract_summary`.

## Files touched

- `apps/api/app/forms/lead_factory.py` — helpers + Contact creation.
- `apps/api/app/forms/inbox.py` — `extract_question`, item dict fields.
- `apps/api/app/forms/schemas.py` — `InboxItemOut` fields.
- `apps/web/app/(app)/incoming/page.tsx` — `Row` redesign.
- `apps/web/lib/types.ts` — `InboxItemOut` type.
- Tests under `apps/api/tests/` (forms).
