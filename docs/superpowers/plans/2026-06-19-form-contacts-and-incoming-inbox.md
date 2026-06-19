# Form-lead Contacts + Richer «Входящие» Inbox — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-create a `Contact` (primary ЛПР) from web-form submissions that carry an email/phone, and make the `/incoming` inbox show who wrote, clickable contacts, the isolated question, and explicit source.

**Architecture:** Pure extraction helpers in `app/forms/lead_factory.py` read both clean per-field payloads (our embed) and the `Label: value` blob real sites POST. `create_lead_from_submission` uses them to spawn a Contact. The `/incoming` read-model (`app/forms/inbox.py`) exposes `contact_name`/`question`/`summary`/`source_domain`; the `Row` component renders them with `tel:`/`mailto:` chips.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend), Next.js 15 App Router + TypeScript + Tailwind (frontend). Backend tests are mock-only pytest (sqlalchemy stubbed at import — see `tests/test_public_submit.py`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-19-form-contacts-and-incoming-inbox-design.md`.
- Do NOT change the drinkx.ru website / embed, do NOT expand the email/phone field mapping in `_project_payload`, do NOT backfill historical leads.
- Contact provenance is fixed: `source="webform"`, `confidence="high"`, `verified_status="verified"`.
- Bare form key `name` stays mapped to `company_name` (untouched) — person-name keys are a separate set excluding `name`.
- Spacing scale 4-8-12-16-24-32px; no Inter/Roboto/Arial. Match existing file style.
- Frontend pre-PR: `npm run typecheck` + `npm run lint` + `pnpm build` from `apps/web` (tsc alone is not enough for App Router).
- Execute on a feature branch cut from the current branch (so it includes the committed spec): `git switch -c feat/form-contacts-incoming-inbox`.

## File Structure

- `apps/api/app/forms/lead_factory.py` — **modify**: add `_lookup`, `_clean`, `_parse_labeled_block`, `extract_person_name`, `extract_question`, `extract_summary`; add Contact creation in `create_lead_from_submission`; new import `from app.contacts.models import Contact`.
- `apps/api/app/forms/inbox.py` — **modify**: drop `_SNIPPET_KEYS`/`extract_snippet`, import the extractors from `lead_factory`, populate `contact_name`/`question`/`summary` in the item dict.
- `apps/api/app/forms/schemas.py` — **modify**: `InboxItemOut` — drop `snippet`, add `contact_name`/`question`/`summary`.
- `apps/api/tests/test_public_submit.py` — **modify**: replace the `extract_snippet` test with extractor tests; add Contact-creation tests.
- `apps/web/lib/types.ts` — **modify**: `InboxItemOut` — drop `snippet`, add `contact_name`/`question`/`summary`.
- `apps/web/app/(app)/incoming/page.tsx` — **modify**: redesign `Row`, add `ContactChip`.

---

## Task 1: Extraction helpers in `lead_factory.py`

**Files:**
- Modify: `apps/api/app/forms/lead_factory.py`
- Test: `apps/api/tests/test_public_submit.py`

**Interfaces:**
- Produces:
  - `extract_person_name(payload: dict, *, limit: int = 120) -> str | None`
  - `extract_question(payload: dict, *, limit: int = 200) -> str | None`
  - `extract_summary(payload: dict, *, limit: int = 200) -> str`
  - module constants `PERSON_NAME_KEYS`, `QUESTION_KEYS` (tuples of normalized keys)

- [ ] **Step 1: Replace the old `extract_snippet` test with extractor tests**

In `apps/api/tests/test_public_submit.py`, delete the existing `test_inbox_extract_snippet_prefers_message_keys` function (the last test in the file, importing `from app.forms.inbox import extract_snippet`) and add in its place:

```python
# ===========================================================================
# 11. Submission field extraction (lead_factory helpers)
# ===========================================================================

def test_extract_question_clean_field():
    from app.forms.lead_factory import extract_question
    assert extract_question({"comment": "Нужен S300"}) == "Нужен S300"


def test_extract_question_capitalized_key_regression():
    # The old extract_snippet matched only lowercase keys; normalized
    # lookup must now match a capitalized "Сообщение".
    from app.forms.lead_factory import extract_question
    assert extract_question({"Сообщение": "Привет"}) == "Привет"


def test_extract_question_from_blob():
    from app.forms.lead_factory import extract_question
    blob = (
        "Имя: Константин Осипов\nСегмент: Другое\n"
        "Сообщение: какую проблему решает дринкс?\nИсточник: website"
    )
    assert extract_question({"message": blob}) == "какую проблему решает дринкс?"


def test_extract_question_structured_only_blob_is_none():
    from app.forms.lead_factory import extract_question
    blob = "Способ связи: test\nФормат заведения: Клуб\nИсточник: лендинг"
    assert extract_question({"message": blob}) is None


def test_extract_question_absent_is_none():
    from app.forms.lead_factory import extract_question
    assert extract_question({"phone": "+7 900 000-00-00"}) is None
    assert extract_question(None) is None


def test_extract_person_name_clean_field():
    from app.forms.lead_factory import extract_person_name
    assert extract_person_name({"имя": "Константин Осипов"}) == "Константин Осипов"


def test_extract_person_name_from_blob():
    from app.forms.lead_factory import extract_person_name
    blob = "Имя: Константин Осипов\nСегмент: Другое\nСообщение: вопрос"
    assert extract_person_name({"message": blob}) == "Константин Осипов"


def test_extract_person_name_absent_is_none():
    from app.forms.lead_factory import extract_person_name
    assert extract_person_name({"email": "x@y.io"}) is None


def test_extract_summary_structured_fields():
    from app.forms.lead_factory import extract_summary
    blob = "Способ связи: test\nФормат заведения: Клуб\nИсточник: лендинг"
    assert extract_summary({"message": blob}) == "Способ связи: test · Формат заведения: Клуб"


def test_extract_summary_excludes_message_name_and_source():
    from app.forms.lead_factory import extract_summary
    blob = (
        "Имя: К\nСегмент: Другое\nИнтересует модель: S300\n"
        "Сообщение: вопрос\nИсточник: website"
    )
    assert extract_summary({"message": blob}) == "Сегмент: Другое · Интересует модель: S300"


def test_extract_summary_no_blob_is_empty():
    from app.forms.lead_factory import extract_summary
    assert extract_summary({"comment": "просто текст"}) == ""
    assert extract_summary({"phone": "+7"}) == ""
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_public_submit.py -k "extract_question or extract_person_name or extract_summary" -v`
Expected: FAIL — `ImportError: cannot import name 'extract_question' from 'app.forms.lead_factory'`.

- [ ] **Step 3: Add the helpers to `lead_factory.py`**

In `apps/api/app/forms/lead_factory.py`, immediately after the existing `_normalize_key` function (around line 71), add:

```python
# Person-name keys (clean fields). Bare "name" stays mapped to company_name,
# so it is intentionally excluded here.
PERSON_NAME_KEYS: tuple[str, ...] = (
    "имя", "фио", "ф.и.о.", "контактное лицо", "ваше имя",
    "как вас зовут", "contact name", "contact_name", "контакт",
)
# Free-text message keys, priority order.
QUESTION_KEYS: tuple[str, ...] = (
    "вопрос", "question", "сообщение", "message",
    "комментарий", "comment", "comments",
)
# Normalized blob labels that count as the free-text message.
_MESSAGE_LABELS = {"сообщение", "вопрос", "message", "comment", "comments", "комментарий"}
# Normalized blob labels excluded from the structured-fields summary.
_SUMMARY_EXCLUDE = _MESSAGE_LABELS | {
    "имя", "фио", "ф.и.о.", "контактное лицо", "ваше имя", "name", "контакт",
    "источник", "source", "email", "e-mail", "почта",
    "телефон", "phone", "тел", "mobile",
}


def _clean(text: str) -> str:
    """Collapse all runs of whitespace (incl. newlines) to single spaces."""
    return " ".join(str(text).split())


def _lookup(payload: Any, keys: tuple[str, ...]) -> str | None:
    """First non-empty value whose normalized key matches one of `keys`.
    Preserves the value's internal whitespace (callers collapse if needed)."""
    if not isinstance(payload, dict):
        return None
    norm_map = {_normalize_key(str(k)): v for k, v in payload.items()}
    for key in keys:
        v = norm_map.get(_normalize_key(key))
        if v not in (None, ""):
            return str(v).strip()
    return None


def _parse_labeled_block(text: str | None) -> list[tuple[str, str]]:
    """Split a newline-separated `Label: value` blob into ordered
    (label, value) pairs. Accepts ASCII ':' and full-width '：'. Returns
    [] when the text is not such a block."""
    pairs: list[tuple[str, str]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        positions = [line.find(c) for c in (":", "：") if line.find(c) > 0]
        if not positions:
            continue
        idx = min(positions)
        label = line[:idx].strip()
        value = line[idx + 1:].strip()
        if label and value:
            pairs.append((label, value))
    return pairs


def extract_person_name(payload: Any, *, limit: int = 120) -> str | None:
    """Contact person's name: a clean person-name field, else the `Имя:`/
    `ФИО:` line inside the message blob, else None."""
    v = _lookup(payload, PERSON_NAME_KEYS)
    if v:
        return _clean(v)[:limit]
    pairs = _parse_labeled_block(_lookup(payload, QUESTION_KEYS))
    name = next(
        (val for lbl, val in pairs if _normalize_key(lbl) in PERSON_NAME_KEYS),
        None,
    )
    return _clean(name)[:limit] if name else None


def extract_question(payload: Any, *, limit: int = 200) -> str | None:
    """The visitor's free-text message, or None when there is none
    (e.g. landing forms carrying only structured fields)."""
    raw = _lookup(payload, QUESTION_KEYS)
    if not raw:
        return None
    pairs = _parse_labeled_block(raw)
    if len(pairs) >= 2:  # a real Label:value blob, not a one-line message
        msg = next((val for lbl, val in pairs if _normalize_key(lbl) in _MESSAGE_LABELS), None)
        return _clean(msg)[:limit] if msg else None
    return _clean(raw)[:limit]


def extract_summary(payload: Any, *, limit: int = 200) -> str:
    """One-line recap of a structured blob (used when there is no
    free-text question): `Label: value · Label: value`, contact fields
    and noise excluded. Empty when the payload is not a blob."""
    pairs = _parse_labeled_block(_lookup(payload, QUESTION_KEYS))
    if len(pairs) < 2:
        return ""
    kept = [f"{lbl}: {val}" for lbl, val in pairs if _normalize_key(lbl) not in _SUMMARY_EXCLUDE]
    return _clean(" · ".join(kept))[:limit]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && python -m pytest tests/test_public_submit.py -k "extract_question or extract_person_name or extract_summary" -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/forms/lead_factory.py apps/api/tests/test_public_submit.py
git commit -m "feat(forms): submission field extractors (name/question/summary)

Normalized fuzzy lookup + Label:value blob parsing. Handles both clean
per-field payloads and the blob real sites POST. Replaces the
case-sensitive extract_snippet.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Auto-create Contact in `create_lead_from_submission`

**Files:**
- Modify: `apps/api/app/forms/lead_factory.py` (import + insert after the lead flush)
- Test: `apps/api/tests/test_public_submit.py`

**Interfaces:**
- Consumes: `extract_person_name` (Task 1), `Contact` ORM model (`app.contacts.models`), `Lead.primary_contact_id` (nullable UUID column).
- Produces: side effect — a `Contact` row per submission with email/phone, and `lead.primary_contact_id` set when previously None.

- [ ] **Step 1: Write the failing tests**

In `apps/api/tests/test_public_submit.py`, append:

```python
# ===========================================================================
# 12. Contact auto-creation from submission
# ===========================================================================

def _contact_spies():
    """Returns (LeadSpy, ActivitySpy, ContactSpy, captured) where captured
    collects the kwargs each Contact was built with."""
    captured: list[dict] = []

    class _LeadSpy:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()
            self.primary_contact_id = None
            if not hasattr(self, "email"):
                self.email = None
            if not hasattr(self, "phone"):
                self.phone = None

    class _ActivitySpy:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class _ContactSpy:
        def __init__(self, **kw):
            captured.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()

    return _LeadSpy, _ActivitySpy, _ContactSpy, captured


async def _run_factory(payload):
    LeadSpy, ActivitySpy, ContactSpy, captured = _contact_spies()
    db = _make_db()
    pipelines_module = ModuleType("app.pipelines")
    repos_module = ModuleType("app.pipelines.repositories")
    repos_module.get_default_first_stage = AsyncMock(return_value=None)
    pipelines_module.repositories = repos_module

    from app.forms.lead_factory import create_lead_from_submission

    with patch("app.forms.lead_factory.Lead", LeadSpy), \
         patch("app.forms.lead_factory.Activity", ActivitySpy), \
         patch("app.forms.lead_factory.Contact", ContactSpy), \
         patch.dict(sys.modules, {
             "app.pipelines": pipelines_module,
             "app.pipelines.repositories": repos_module,
         }):
        lead = await create_lead_from_submission(
            db, form=_make_form(), payload=payload, source_domain=None,
        )
    return lead, captured


@pytest.mark.asyncio
async def test_contact_created_with_email_phone_and_primary_set():
    lead, captured = await _run_factory({
        "company_name": "Stars", "email": "x@y.io",
        "phone": "+79990001122", "имя": "Иван Петров",
    })
    assert len(captured) == 1
    assert captured[0]["email"] == "x@y.io"
    assert captured[0]["phone"] == "+79990001122"
    assert captured[0]["name"] == "Иван Петров"
    assert captured[0]["source"] == "webform"
    assert captured[0]["verified_status"] == "verified"
    assert captured[0]["confidence"] == "high"
    assert lead.primary_contact_id is not None


@pytest.mark.asyncio
async def test_contact_name_falls_back_to_email_when_no_name():
    _, captured = await _run_factory({"company_name": "Stars", "email": "x@y.io"})
    assert len(captured) == 1
    assert captured[0]["name"] == "x@y.io"


@pytest.mark.asyncio
async def test_no_contact_when_no_email_or_phone():
    lead, captured = await _run_factory({
        "company_name": "Bar",
        "message": "Способ связи: test\nФормат заведения: Клуб",
    })
    assert captured == []
    assert lead.primary_contact_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_public_submit.py -k "contact" -v`
Expected: FAIL — `AttributeError: <module 'app.forms.lead_factory'> does not have the attribute 'Contact'` (the patch target does not exist yet).

- [ ] **Step 3: Add the Contact import**

In `apps/api/app/forms/lead_factory.py`, in the top import block (next to `from app.activity.models import Activity` and `from app.leads.models import Lead`), add:

```python
from app.contacts.models import Contact
```

- [ ] **Step 4: Insert Contact creation after the lead flush**

In `create_lead_from_submission`, find:

```python
    lead = Lead(**lead_kwargs)
    session.add(lead)
    await session.flush()
```

Immediately after it, insert:

```python
    # Web-form contact (ADR-012): a submission carrying an email or phone
    # becomes a first-class Contact + primary ЛПР, so the lead card's
    # «Контакты» tab and one-click call/email work without manual entry.
    if lead.email or lead.phone:
        contact = Contact(
            workspace_id=lead.workspace_id,
            lead_id=lead.id,
            name=(extract_person_name(payload) or lead.email or lead.phone or "Контакт с формы")[:120],
            email=lead.email,
            phone=lead.phone,
            source="webform",
            confidence="high",
            verified_status="verified",
        )
        session.add(contact)
        await session.flush()
        if lead.primary_contact_id is None:
            lead.primary_contact_id = contact.id
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && python -m pytest tests/test_public_submit.py -k "contact" -v`
Expected: PASS (3 tests). If `safe_evaluate_trigger` import errors in the stub env, add `patch("app.automation_builder.services.safe_evaluate_trigger", new=AsyncMock())` to the `with` block in `_run_factory` (mirrors how other tests isolate side-effects).

- [ ] **Step 6: Run the whole forms test module**

Run: `cd apps/api && python -m pytest tests/test_public_submit.py -v`
Expected: PASS (all tests, including the pre-existing submit/embed/autoreply ones).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/forms/lead_factory.py apps/api/tests/test_public_submit.py
git commit -m "feat(forms): create a Contact + primary ЛПР from form submissions

A submission with an email or phone now spawns a verified webform Contact
linked to the lead and set as primary contact when none exists.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Inbox read-model exposes name/question/summary

**Files:**
- Modify: `apps/api/app/forms/inbox.py`
- Modify: `apps/api/app/forms/schemas.py`

**Interfaces:**
- Consumes: `extract_person_name`, `extract_question`, `extract_summary` (Task 1).
- Produces: `InboxItemOut` gains `contact_name: str | None`, `question: str | None`, `summary: str`; loses `snippet`.

- [ ] **Step 1: Rewrite the head of `inbox.py`**

In `apps/api/app/forms/inbox.py`, delete the `_SNIPPET_KEYS` tuple and the entire `extract_snippet` function (lines ~25-41), and replace them with an import. The top of the file (after the existing `from app.leads.models import Lead`) becomes:

```python
from app.forms.lead_factory import (
    extract_person_name,
    extract_question,
    extract_summary,
)
```

- [ ] **Step 2: Update the item dict in `list_inbox`**

In `list_inbox`, find the `items.append({...})` block and replace the `"snippet": extract_snippet(sub.raw_payload),` line with:

```python
                "contact_name": extract_person_name(sub.raw_payload),
                "question": extract_question(sub.raw_payload),
                "summary": extract_summary(sub.raw_payload),
```

- [ ] **Step 3: Update `__all__`**

At the bottom of `inbox.py`, change:

```python
__all__ = ["extract_snippet", "count_new", "list_inbox"]
```

to:

```python
__all__ = ["count_new", "list_inbox"]
```

- [ ] **Step 4: Update `InboxItemOut` schema**

In `apps/api/app/forms/schemas.py`, in `class InboxItemOut`, delete the line `snippet: str = ""` and add (next to `source_domain`):

```python
    contact_name: str | None = None
    question: str | None = None
    summary: str = ""
```

- [ ] **Step 5: Verify the modules import and tests still collect**

Run: `cd apps/api && python -c "import app.forms.inbox, app.forms.schemas" && python -m pytest tests/test_public_submit.py -q`
Expected: no ImportError; tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/forms/inbox.py apps/api/app/forms/schemas.py
git commit -m "feat(forms): inbox read-model exposes contact_name/question/summary

Drop the all-fields snippet for an isolated question (free text), a
structured-fields summary fallback, and the parsed contact name.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `/incoming` Row redesign (frontend)

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/app/(app)/incoming/page.tsx`

**Interfaces:**
- Consumes: `InboxItemOut` with `contact_name`/`question`/`summary`/`source_domain`/`phone`/`email` (Task 3).

- [ ] **Step 1: Update the TypeScript type**

In `apps/web/lib/types.ts`, in `export interface InboxItemOut`, delete `snippet: string;` and add:

```typescript
  contact_name: string | null;
  question: string | null;
  summary: string;
```

- [ ] **Step 2: Add contact icons to the imports**

In `apps/web/app/(app)/incoming/page.tsx`, change the lucide import line:

```typescript
import { AlertCircle, ArrowRight, CheckCheck, Inbox, Loader2 } from "lucide-react";
```

to:

```typescript
import { AlertCircle, ArrowRight, CheckCheck, Check, Copy, Inbox, Loader2, Mail, Phone } from "lucide-react";
```

- [ ] **Step 3: Add the `ContactChip` component**

In `apps/web/app/(app)/incoming/page.tsx`, add this component just above the `Row` function:

```tsx
function ContactChip({
  href,
  icon,
  label,
  copyText,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  copyText: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="inline-flex items-center rounded-full bg-brand-bg border border-brand-border overflow-hidden">
      <a
        href={href}
        onClick={(e) => e.stopPropagation()}
        className="inline-flex items-center gap-1.5 px-3 py-1 type-caption font-medium text-brand-muted-strong hover:text-brand-accent transition-colors"
      >
        {icon}
        {label}
      </a>
      <button
        type="button"
        aria-label="Копировать"
        onClick={(e) => {
          e.stopPropagation();
          void navigator.clipboard?.writeText(copyText);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="px-2 py-1 text-brand-muted hover:text-brand-accent border-l border-brand-border transition-colors"
      >
        {copied ? <Check size={11} /> : <Copy size={11} />}
      </button>
    </span>
  );
}
```

- [ ] **Step 4: Replace the `Row` component body**

In `apps/web/app/(app)/incoming/page.tsx`, replace the entire existing `Row` function with:

```tsx
function Row({ item, onOpenLead }: { item: InboxItemOut; onOpenLead: () => void }) {
  const st = statusLabel(item);
  const company = item.company_name || "Без названия";
  return (
    <div
      onClick={onOpenLead}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onOpenLead();
      }}
      className="relative rounded-card border border-brand-border bg-white px-4 py-3.5 pl-5 cursor-pointer transition-colors hover:border-brand-muted"
    >
      {item.is_new && (
        <span className="absolute left-2 top-5 w-2 h-2 rounded-full bg-brand-accent" />
      )}

      {/* Who */}
      <div className="flex items-center gap-2">
        <span className="text-[15px] font-bold text-brand-primary truncate">
          {item.contact_name || company}
        </span>
        {item.contact_name && (
          <span className="text-sm text-brand-muted truncate">{company}</span>
        )}
        <span className="ml-auto text-xs text-brand-muted whitespace-nowrap">
          {relativeTime(item.created_at)}
        </span>
      </div>

      {/* Clickable contacts */}
      {(item.phone || item.email) && (
        <div className="flex gap-2 mt-2 flex-wrap">
          {item.phone && (
            <ContactChip
              href={`tel:${item.phone}`}
              icon={<Phone size={12} />}
              label={item.phone}
              copyText={item.phone}
            />
          )}
          {item.email && (
            <ContactChip
              href={`mailto:${item.email}`}
              icon={<Mail size={12} />}
              label={item.email}
              copyText={item.email}
            />
          )}
        </div>
      )}

      {/* Question / structured summary */}
      {item.question ? (
        <p className="text-sm text-brand-muted-strong mt-2 leading-snug line-clamp-2">
          <span className="font-semibold">Вопрос клиента:</span> {item.question}
        </p>
      ) : item.summary ? (
        <p className="text-sm text-brand-muted mt-2 leading-snug line-clamp-2">
          <span className="font-semibold">Из заявки:</span> {item.summary}
        </p>
      ) : null}

      {/* Source + status */}
      <div className="flex items-center gap-2 mt-2.5 flex-wrap">
        <span className={`${T.mono} text-[10px] uppercase tracking-wider px-2 py-1 rounded-md bg-brand-bg text-brand-muted`}>
          {item.channel}
        </span>
        {item.source_domain && (
          <span className="text-xs text-brand-muted">{item.source_domain}</span>
        )}
        <StatusPill st={st} />
        <span className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-brand-accent">
          Открыть лида <ArrowRight size={12} />
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Typecheck, lint, build**

Run: `cd apps/web && npm run typecheck && npm run lint && pnpm build`
Expected: all succeed. (No more `item.snippet` references; `T` is already imported in this file.)

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/types.ts "apps/web/app/(app)/incoming/page.tsx"
git commit -m "feat(incoming): who + clickable contacts + isolated question + source

Row now shows contact name, tel:/mailto: chips with copy, the isolated
client question (or a structured summary for landing forms), and the
source domain alongside the channel.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Live verification

**Files:** none (manual, browser).

- [ ] **Step 1: Verify the Осипов submission**

On a running build, open `/leads/d3993b08-f020-407a-927c-8bd73482aae0` → «Контакты» tab. *Note:* this is a historical lead — no backfill, so it will still be empty. Instead verify with a **new** test submission (or confirm via a fresh заявка) that a contact appears and is primary ЛПР.

- [ ] **Step 2: Verify `/incoming`**

Open `/incoming`. Expected: for a website-style заявка — bold contact name + company, `tel:`/`mailto:` chips (with copy), "Вопрос клиента: …", and `channel + domain`. For a landing заявка (станция/бар/меню) — no empty "Вопрос" block; instead "Из заявки: Способ связи: … · Формат заведения: …", and no contact chips (no email/phone in those payloads).

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/form-contacts-incoming-inbox
```

(Only after the user confirms they want it pushed / a PR opened.)

---

## Self-Review

**Spec coverage:**
- Feature A (Contact creation, primary ЛПР, verified/webform/high, name fallback, email-or-phone gate) → Task 2. ✓
- Extraction helpers + case-sensitivity fix → Task 1. ✓
- Feature B backend (contact_name/question/summary/source_domain, drop snippet) → Task 3. ✓
- Feature B frontend (who, clickable contacts, source, graceful question) → Task 4. ✓
- Graceful empty question / structured summary → `extract_summary` (Task 1) + Row branch (Task 4). ✓
- Out-of-scope items (no website change, no mapping expansion, no backfill, comment left as-is, no contact dedup) → respected; backfill called out in Task 5 Step 1. ✓

**Placeholder scan:** No TBD/TODO; every code step carries full code. ✓

**Type consistency:** `extract_question`/`extract_summary`/`extract_person_name` signatures identical across Tasks 1-3; `InboxItemOut` fields identical in `schemas.py` (Task 3) and `types.ts` (Task 4); `ContactChip` props match call sites in `Row` (Task 4). ✓
