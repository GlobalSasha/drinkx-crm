# Sprint 3.6 — Landing Forms Attribution · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface multi-landing attribution end-to-end — managers see which landing brought each lead, can filter the pool by form, and see per-form stats; self-coded landings have a docs page with two integration patterns.

**Architecture:** Three new read-only enrichments on `LeadOut` (`source_form_id`, `source_form_name`, `latest_utm`) computed at the read path via JOIN on `web_forms` and a follow-up SELECT on the latest `form_submission` Activity. New `GET /api/forms/{id}/stats` aggregating from `form_submissions` + leads. Frontend wires a clickable chip on the Lead Card header, an «Источник» section in `DealAndAITab`, a filter dropdown + per-row chip on `/leads-pool`, a small Globe icon on the pipeline kanban for form-sourced leads, and a stats card on `/forms`. Docs file `docs/landings.md` ships two patterns (embed.js + copy-paste React).

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy async, Pydantic, pytest with mock-stubbed sqlalchemy (per existing `apps/api/tests/test_webforms.py` pattern). Frontend: Next.js 15 App Router, React, TypeScript strict, Tailwind, TanStack Query, shadcn/ui.

**Spec:** `docs/SPRINT_3_6_LANDING_FORMS_ATTRIBUTION.md`

**Branch:** `sprint/3.6-landing-forms-attribution` — branch from `main` after Sprint 3.5 (PR #47) merges.

---

## File map

**Backend (`apps/api/`):**
- Modify `app/leads/schemas.py` — add three fields to `LeadOut`.
- Modify `app/leads/repositories.py` — extend list queries with `form_id` filter; add helper that resolves `source_form_id`/`source_form_name` from the lead's `source` string via JOIN on `web_forms` by slug; add helper that reads `latest_utm` from the most recent `form_submission` Activity.
- Modify `app/leads/services.py` — thread the new `form_id` arg through `list_assigned` / `list_pool`.
- Modify `app/leads/routers.py` — accept `form_id: UUID | None = None` query param on the two list endpoints.
- Create `app/forms/services.py::get_form_stats` (extension of existing file).
- Modify `app/forms/schemas.py` — add `FormStatsOut`.
- Modify `app/forms/routers.py` — add `GET /{form_id}/stats`.

**Backend tests (`apps/api/tests/`):**
- Create `test_leads_source_enrichment.py` — covers `source_form_id`/`source_form_name`/`latest_utm` resolution.
- Create `test_form_stats.py` — covers `get_form_stats` outputs.

**Frontend (`apps/web/`):**
- Modify `lib/types.ts` — add three fields to `LeadOut`; add `FormStatsOut` interface.
- Modify `lib/hooks/use-leads.ts` — pass `form_id` query param.
- Modify `lib/hooks/use-forms.ts` — add `useFormStats(formId)`.
- Modify `components/lead-card/LeadCard.tsx` — render source chip in the header.
- Create `components/lead-card/SourceSection.tsx` — «Источник» block (form name + source_domain + UTM table + raw_payload disclosure).
- Modify `components/lead-card/DealAndAITab.tsx` — render `<SourceSection>` between «Параметры сделки» and «AI Бриф».
- Modify `components/pipeline/PipelineLeadCard.tsx` — 10px Globe icon next to company name when `lead.source LIKE 'form:%'`.
- Modify `app/(app)/leads-pool/page.tsx` — «Источник» dropdown filter + small chip on each row.
- Create `components/forms/FormStatsCard.tsx` — per-form stats card.
- Modify `app/(app)/forms/page.tsx` — render `<FormStatsCard>` under each form row.

**Docs:**
- Create `docs/landings.md` — two patterns + UTM passthrough + smoke checklist.

---

## Task 1 — Backend: add `source_form_id`, `source_form_name`, `latest_utm` to `LeadOut`

**Files:**
- Modify: `apps/api/app/leads/schemas.py` (after the existing `LeadOut` fields, around line 110)
- Modify: `apps/api/app/leads/repositories.py` (the `_populate_extras` helper around line 39 and the two list queries around lines 78 and 144)
- Create: `apps/api/tests/test_leads_source_enrichment.py`

### Step 1.1 — Write the failing test

- [ ] Create `apps/api/tests/test_leads_source_enrichment.py` with the following content:

```python
"""Sprint 3.6 G1 — LeadOut source/UTM enrichment tests.

Mirrors the mock-stubbed sqlalchemy pattern from test_webforms.py so the
test suite doesn't pull the declarative base. Covers:
  - `parse_form_slug_from_source` returns the slug or None
  - `resolve_form_for_source` returns (id, name) for a known slug, None
    for an unknown one
  - `latest_form_utm_for_lead` returns the most recent
    `form_submission` Activity's payload_json['utm'] or None
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


# Reuse the sqlalchemy stub helper from test_webforms.py
from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_parse_form_slug_from_source_prefix():
    from app.leads import repositories as repo

    assert repo.parse_form_slug_from_source("form:horeca-msk") == "horeca-msk"
    assert repo.parse_form_slug_from_source("form:") is None
    assert repo.parse_form_slug_from_source(None) is None
    assert repo.parse_form_slug_from_source("manual") is None
    assert repo.parse_form_slug_from_source("import_csv") is None


@pytest.mark.asyncio
async def test_resolve_form_for_source_returns_id_and_name():
    from app.leads import repositories as repo

    form_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        first=lambda: (form_id, "HoReCa МСК"),
    )

    out = await repo.resolve_form_for_source(db, "form:horeca-msk")

    assert out == (form_id, "HoReCa МСК")


@pytest.mark.asyncio
async def test_resolve_form_for_source_returns_none_for_non_form_source():
    from app.leads import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock()
    out = await repo.resolve_form_for_source(db, "manual")

    assert out is None
    db.execute.assert_not_awaited()  # short-circuit, no DB hit


@pytest.mark.asyncio
async def test_latest_form_utm_for_lead_returns_dict():
    from app.leads import repositories as repo

    lead_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        scalar_one_or_none=lambda: {
            "utm": {"utm_source": "vk", "utm_campaign": "horeca-q3"}
        },
    )

    out = await repo.latest_form_utm_for_lead(db, lead_id)

    assert out == {"utm_source": "vk", "utm_campaign": "horeca-q3"}


@pytest.mark.asyncio
async def test_latest_form_utm_for_lead_returns_none_when_no_activity():
    from app.leads import repositories as repo

    lead_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        scalar_one_or_none=lambda: None,
    )

    out = await repo.latest_form_utm_for_lead(db, lead_id)

    assert out is None
```

### Step 1.2 — Run the test, confirm it fails

- [ ] Run: `cd apps/api && pytest tests/test_leads_source_enrichment.py -v`
- [ ] Expected: failure with `AttributeError: module 'app.leads.repositories' has no attribute 'parse_form_slug_from_source'` (or similar — function doesn't exist yet).

### Step 1.3 — Add the helpers to `apps/api/app/leads/repositories.py`

- [ ] Open `apps/api/app/leads/repositories.py` and add these helpers near the top of the file, after the existing imports but before `_populate_extras`:

```python
def parse_form_slug_from_source(source: str | None) -> str | None:
    """Extract the form slug from `lead.source` if it carries one.

    `lead_factory.create_lead_from_submission` writes
    `source = f"form:{slug}"` for form-originated leads. Returns the
    slug (no prefix) or None for non-form / malformed sources.
    """
    if not source:
        return None
    prefix = "form:"
    if not source.startswith(prefix):
        return None
    slug = source[len(prefix):].strip()
    return slug or None


async def resolve_form_for_source(
    db: AsyncSession, source: str | None
) -> tuple[uuid.UUID, str] | None:
    """Look up the WebForm by slug parsed from `source`. Returns
    (form_id, form_name) or None when the source is not a form or the
    form has been deleted (FK SET NULL on the foreign key path)."""
    slug = parse_form_slug_from_source(source)
    if slug is None:
        return None

    from app.forms.models import WebForm

    result = await db.execute(
        select(WebForm.id, WebForm.name).where(WebForm.slug == slug).limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return (row[0], row[1])


async def latest_form_utm_for_lead(
    db: AsyncSession, lead_id: uuid.UUID
) -> dict | None:
    """Return the UTM dict from the most recent `form_submission`
    Activity for the lead, or None when no such Activity exists."""
    from app.activity.models import Activity

    result = await db.execute(
        select(Activity.payload_json)
        .where(Activity.lead_id == lead_id, Activity.type == "form_submission")
        .order_by(Activity.created_at.desc())
        .limit(1)
    )
    payload = result.scalar_one_or_none()
    if not payload:
        return None
    utm = payload.get("utm") if isinstance(payload, dict) else None
    if not utm or not isinstance(utm, dict):
        return None
    return dict(utm)
```

### Step 1.4 — Run the test, confirm it passes

- [ ] Run: `cd apps/api && pytest tests/test_leads_source_enrichment.py -v`
- [ ] Expected: all 5 tests PASS.

### Step 1.5 — Add the three fields to the `LeadOut` Pydantic schema

- [ ] Open `apps/api/app/leads/schemas.py`. Find the `LeadOut` class (around line 66). Add these three fields right after `primary_contact_name` (around line 92):

```python
    # Sprint 3.6 G1 — landing-form attribution. Resolved at the read
    # path, never stored. `source_form_id` is the FK target so the
    # frontend chip can deep-link to `/leads-pool?form_id=<id>`.
    source_form_id: UUID | None = None
    source_form_name: str | None = None
    latest_utm: dict | None = None
```

### Step 1.6 — Populate the new fields in `_populate_extras`

- [ ] Open `apps/api/app/leads/repositories.py`. The current `_populate_extras` (around line 39) attaches `primary_contact_name`. Extend it to call the new helpers on each row.

Replace `_populate_extras` with:

```python
async def _populate_extras(
    rows: list,
    *,
    db: AsyncSession | None = None,
) -> list[Lead]:
    """Walk the (Lead, primary_contact_name, open_tasks, open_followups)
    tuples and attach the joined values to the Lead instance so the
    Pydantic schema can read them as if they were ORM columns.

    Sprint 3.6: also resolves `source_form_id`/`source_form_name` via
    a WebForm JOIN and `latest_utm` via the latest form_submission
    Activity. Both are best-effort — if the form was deleted or the
    Activity row is missing, the fields stay None.
    """
    leads: list[Lead] = []
    for lead, contact_name, open_tasks, open_followups in rows:
        lead.primary_contact_name = contact_name  # type: ignore[attr-defined]
        lead.open_tasks_count = open_tasks  # type: ignore[attr-defined]
        lead.open_followups_count = open_followups  # type: ignore[attr-defined]
        # Defaults so Pydantic doesn't complain even if `db` is None.
        lead.source_form_id = None  # type: ignore[attr-defined]
        lead.source_form_name = None  # type: ignore[attr-defined]
        lead.latest_utm = None  # type: ignore[attr-defined]
        leads.append(lead)

    if db is not None:
        for lead in leads:
            form = await resolve_form_for_source(db, lead.source)
            if form is not None:
                lead.source_form_id = form[0]  # type: ignore[attr-defined]
                lead.source_form_name = form[1]  # type: ignore[attr-defined]
            # Read latest_utm only for form-sourced leads — saves N
            # extra queries on cold leads.
            if lead.source_form_id is not None:
                lead.latest_utm = await latest_form_utm_for_lead(  # type: ignore[attr-defined]
                    db, lead.id
                )

    return leads
```

- [ ] Then update the two call sites in the same file. In `list_leads` (around line 141) change:
  ```python
  return _populate_extras(list(rows_result.all())), total
  ```
  to:
  ```python
  return await _populate_extras(list(rows_result.all()), db=db), total
  ```
- [ ] In `list_pool` (around line 175 region — the analogous return) make the same change.
- [ ] If there is a third caller for a single-lead fetch (search for other `_populate_extras` calls), update it too. Run:
  ```
  grep -n "_populate_extras" apps/api/app/leads/repositories.py
  ```
- [ ] Every caller must `await` and pass `db=db`.

### Step 1.7 — Verify the schema serializes the new fields

- [ ] Add to `apps/api/tests/test_leads_source_enrichment.py`:

```python
def test_lead_out_serializes_new_fields():
    """Sanity: the Pydantic schema accepts source_form_id, source_form_name,
    latest_utm and serializes them in the JSON output."""
    from app.leads.schemas import LeadOut

    # Schema-only check: just confirm the field set includes the new keys.
    fields = LeadOut.model_fields
    assert "source_form_id" in fields
    assert "source_form_name" in fields
    assert "latest_utm" in fields
```

### Step 1.8 — Run the full backend test slice

- [ ] Run: `cd apps/api && pytest tests/test_leads_source_enrichment.py tests/test_webforms.py -v`
- [ ] Expected: all tests pass.

### Step 1.9 — Commit

```bash
git add apps/api/app/leads/repositories.py apps/api/app/leads/schemas.py apps/api/tests/test_leads_source_enrichment.py
git commit -m "feat(leads): G1 — source_form_{id,name} + latest_utm on LeadOut"
```

---

## Task 2 — Backend: `form_id` filter on leads list endpoints

**Files:**
- Modify: `apps/api/app/leads/repositories.py` (functions `list_leads`, `list_pool`)
- Modify: `apps/api/app/leads/services.py` (the two callers)
- Modify: `apps/api/app/leads/routers.py`

### Step 2.1 — Write the failing test

- [ ] Add to `apps/api/tests/test_leads_source_enrichment.py`:

```python
@pytest.mark.asyncio
async def test_list_leads_form_id_filter_short_circuits_for_unknown_form():
    """If form_id is given but doesn't resolve to a slug, list_leads
    returns empty without querying leads — saves a useless full scan."""
    from app.leads import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock()
    # First call: slug lookup → returns None (form deleted)
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

    rows, total = await repo.list_leads(
        db,
        workspace_id=uuid.uuid4(),
        form_id=uuid.uuid4(),
    )

    assert rows == []
    assert total == 0
```

### Step 2.2 — Run, confirm failure

- [ ] Run: `cd apps/api && pytest tests/test_leads_source_enrichment.py::test_list_leads_form_id_filter_short_circuits_for_unknown_form -v`
- [ ] Expected: failure with `TypeError: list_leads() got an unexpected keyword argument 'form_id'`.

### Step 2.3 — Extend `list_leads` and `list_pool` with the filter

- [ ] Open `apps/api/app/leads/repositories.py`. Add a helper above `list_leads`:

```python
async def _slug_for_form_id(
    db: AsyncSession, form_id: uuid.UUID
) -> str | None:
    """Lookup the slug for a given form_id. Returns None when the form
    has been deleted (the filter then short-circuits to empty)."""
    from app.forms.models import WebForm

    result = await db.execute(
        select(WebForm.slug).where(WebForm.id == form_id).limit(1)
    )
    return result.scalar_one_or_none()
```

- [ ] Add `form_id: uuid.UUID | None = None` to the `list_leads` signature, then before the existing filter chain insert:

```python
    if form_id is not None:
        slug = await _slug_for_form_id(db, form_id)
        if slug is None:
            return [], 0  # unknown / deleted form → nothing matches
        base = base.where(Lead.source == f"form:{slug}")
```

- [ ] Do the same in `list_pool` (around line 144) — add the `form_id` parameter and the same short-circuit + filter clause.

### Step 2.4 — Thread `form_id` through the service layer

- [ ] Open `apps/api/app/leads/services.py`. Search for `list_leads(` and `list_pool(` calls. For each list-service that wraps the repo (typically `list_assigned` and `list_pool`), add `form_id: uuid.UUID | None = None` to the signature and pass it through to the repo.

### Step 2.5 — Add the query param on the router

- [ ] Open `apps/api/app/leads/routers.py`. Find the two list endpoints (the `/leads` and `/leads/pool` route handlers). Add a `form_id: UUID | None = Query(None)` parameter to each and pass it to the service.

### Step 2.6 — Run the test, confirm it passes

- [ ] Run: `cd apps/api && pytest tests/test_leads_source_enrichment.py -v`
- [ ] Expected: all tests pass.

### Step 2.7 — Commit

```bash
git add apps/api/app/leads/repositories.py apps/api/app/leads/services.py apps/api/app/leads/routers.py apps/api/tests/test_leads_source_enrichment.py
git commit -m "feat(leads): G2 — form_id filter on /leads and /leads/pool"
```

---

## Task 3 — Backend: `GET /api/forms/{form_id}/stats`

**Files:**
- Modify: `apps/api/app/forms/schemas.py`
- Modify: `apps/api/app/forms/services.py`
- Modify: `apps/api/app/forms/routers.py`
- Create: `apps/api/tests/test_form_stats.py`

### Step 3.1 — Write the failing test

- [ ] Create `apps/api/tests/test_form_stats.py`:

```python
"""Sprint 3.6 G3 — per-form stats."""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_form_stats_schema_shape():
    """FormStatsOut accepts the documented shape."""
    from app.forms.schemas import FormStatsOut

    stats = FormStatsOut(
        submissions_7d=24,
        submissions_30d=87,
        claimed_count=12,
        by_stage={"Новый контакт": 30, "Квалификация": 8},
    )
    assert stats.submissions_7d == 24
    assert stats.by_stage["Квалификация"] == 8


@pytest.mark.asyncio
async def test_get_form_stats_aggregates_three_buckets():
    from app.forms import services as svc

    form_id = uuid.uuid4()
    db = MagicMock()

    # Sequence of awaitable returns: 7d count, 30d count, claimed count,
    # then the by_stage GROUP BY rows.
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one=lambda: 24),  # 7d
            MagicMock(scalar_one=lambda: 87),  # 30d
            MagicMock(scalar_one=lambda: 12),  # claimed
            MagicMock(all=lambda: [
                ("Новый контакт", 30),
                ("Квалификация", 8),
            ]),
        ]
    )

    out = await svc.get_form_stats(db, form_id=form_id)

    assert out.submissions_7d == 24
    assert out.submissions_30d == 87
    assert out.claimed_count == 12
    assert out.by_stage == {"Новый контакт": 30, "Квалификация": 8}
```

### Step 3.2 — Run, confirm failure

- [ ] Run: `cd apps/api && pytest tests/test_form_stats.py -v`
- [ ] Expected: `ImportError: cannot import name 'FormStatsOut' from 'app.forms.schemas'`.

### Step 3.3 — Add the schema

- [ ] Open `apps/api/app/forms/schemas.py`. Append:

```python
class FormStatsOut(BaseModel):
    """Per-form stats card — Sprint 3.6 G3."""
    submissions_7d: int
    submissions_30d: int
    claimed_count: int
    by_stage: dict[str, int]
```

(Make sure `BaseModel` is imported at the top of the file — it already is if the file defines other schemas.)

### Step 3.4 — Add the service

- [ ] Open `apps/api/app/forms/services.py`. Add at the bottom:

```python
async def get_form_stats(
    db: AsyncSession,
    *,
    form_id: uuid.UUID,
) -> FormStatsOut:
    """Aggregate per-form metrics for the admin /forms stats card.

    Four queries instead of one CTE — each is trivially cheap because
    `form_submissions` is indexed on `web_form_id` and the counts hit
    that index directly. Ordering matters: 7d → 30d → claimed → by_stage
    to mirror the tests.
    """
    from datetime import datetime, timedelta, timezone

    from app.forms.models import FormSubmission
    from app.leads.models import Lead
    from app.pipelines.models import Stage

    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    r_7d = await db.execute(
        select(func.count()).select_from(FormSubmission).where(
            FormSubmission.web_form_id == form_id,
            FormSubmission.created_at >= cutoff_7d,
        )
    )
    r_30d = await db.execute(
        select(func.count()).select_from(FormSubmission).where(
            FormSubmission.web_form_id == form_id,
            FormSubmission.created_at >= cutoff_30d,
        )
    )

    # `claimed` = submissions that resolved to a Lead which has been
    # taken out of pool. One JOIN, no DISTINCT needed because a lead
    # is referenced by at most one submission per form.
    r_claimed = await db.execute(
        select(func.count())
        .select_from(FormSubmission)
        .join(Lead, Lead.id == FormSubmission.lead_id)
        .where(
            FormSubmission.web_form_id == form_id,
            Lead.assignment_status == "assigned",
        )
    )

    r_stage = await db.execute(
        select(Stage.name, func.count(Lead.id))
        .select_from(FormSubmission)
        .join(Lead, Lead.id == FormSubmission.lead_id)
        .join(Stage, Stage.id == Lead.stage_id)
        .where(FormSubmission.web_form_id == form_id)
        .group_by(Stage.name)
    )

    return FormStatsOut(
        submissions_7d=int(r_7d.scalar_one() or 0),
        submissions_30d=int(r_30d.scalar_one() or 0),
        claimed_count=int(r_claimed.scalar_one() or 0),
        by_stage={name: int(count) for name, count in r_stage.all()},
    )
```

- [ ] Make sure the top of `services.py` has the needed imports — `uuid`, `from sqlalchemy import select, func`, and `from app.forms.schemas import FormStatsOut`.

### Step 3.5 — Add the route

- [ ] Open `apps/api/app/forms/routers.py`. Add (near the other admin routes):

```python
@router.get("/{form_id}/stats", response_model=FormStatsOut)
async def get_stats(
    form_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin_or_head),
) -> FormStatsOut:
    """Per-form aggregates for the admin stats card."""
    return await services.get_form_stats(db, form_id=form_id)
```

- [ ] Ensure `FormStatsOut` is imported from `app.forms.schemas` at the top of the file.

### Step 3.6 — Run, confirm pass

- [ ] Run: `cd apps/api && pytest tests/test_form_stats.py -v`
- [ ] Expected: both tests PASS.

### Step 3.7 — Commit

```bash
git add apps/api/app/forms/schemas.py apps/api/app/forms/services.py apps/api/app/forms/routers.py apps/api/tests/test_form_stats.py
git commit -m "feat(forms): G3 — GET /forms/{id}/stats per-form aggregates"
```

---

## Task 4 — Frontend types + hooks

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/hooks/use-leads.ts`
- Modify: `apps/web/lib/hooks/use-forms.ts`

### Step 4.1 — Add fields to `LeadOut` and create `FormStatsOut`

- [ ] Open `apps/web/lib/types.ts`. Find `export interface LeadOut` (around line 87). After `primary_contact_name`, add:

```typescript
  // Sprint 3.6 G1 — landing-form attribution. Backend resolves these
  // at the read path; they are read-only on the frontend.
  source_form_id: string | null;
  source_form_name: string | null;
  latest_utm: Record<string, string> | null;
```

- [ ] At the bottom of `types.ts`, add the stats interface:

```typescript
// Sprint 3.6 G3 — per-form stats card.
export interface FormStatsOut {
  submissions_7d: number;
  submissions_30d: number;
  claimed_count: number;
  by_stage: Record<string, number>;
}
```

### Step 4.2 — Pass `form_id` through `useLeads`

- [ ] Open `apps/web/lib/hooks/use-leads.ts`. Find the filter type / params object the hook accepts. Add `form_id?: string` to it and append `form_id` to the query-string builder. (Pattern is identical to `segment`, `city`, etc. — copy that pattern.)

### Step 4.3 — Add `useFormStats`

- [ ] Open `apps/web/lib/hooks/use-forms.ts`. Append a new hook:

```typescript
export function useFormStats(formId: string | undefined) {
  return useQuery<FormStatsOut, ApiError>({
    queryKey: ["form-stats", formId],
    queryFn: () => api.get<FormStatsOut>(`/forms/${formId}/stats`),
    enabled: !!formId,
    staleTime: 60_000,
  });
}
```

- [ ] Ensure the file imports `useQuery`, `api`, `ApiError`, and adds `FormStatsOut` to the type import from `@/lib/types`.

### Step 4.4 — Verify typecheck

- [ ] Run: `cd apps/web && npm run typecheck`
- [ ] Expected: clean (no new errors).

### Step 4.5 — Commit

```bash
git add apps/web/lib/types.ts apps/web/lib/hooks/use-leads.ts apps/web/lib/hooks/use-forms.ts
git commit -m "feat(types,hooks): G4 — LeadOut source fields + useFormStats hook"
```

---

## Task 5 — Frontend: Lead Card source chip + `SourceSection`

**Files:**
- Modify: `apps/web/components/lead-card/LeadCard.tsx`
- Create: `apps/web/components/lead-card/SourceSection.tsx`
- Modify: `apps/web/components/lead-card/DealAndAITab.tsx`

### Step 5.1 — Create the `SourceSection` component

- [ ] Create `apps/web/components/lead-card/SourceSection.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChevronDown, Globe, Link as LinkIcon } from "lucide-react";
import Link from "next/link";
import type { LeadOut } from "@/lib/types";
import { useFeed } from "@/lib/hooks/use-feed";
import { C } from "@/lib/design-system";

interface Props {
  lead: LeadOut;
}

// Render only when the lead was sourced from a form. The chip on the
// header (in LeadCard.tsx) handles the always-visible signal; this
// section is the structured drill-down inside DealAndAITab.
export function SourceSection({ lead }: Props) {
  const isFormSourced =
    typeof lead.source === "string" && lead.source.startsWith("form:");
  if (!isFormSourced) return null;

  return (
    <section className="bg-white rounded-2xl border border-brand-border p-5">
      <header className="flex items-center gap-2 mb-4">
        <Globe size={16} className="text-brand-accent" />
        <h2 className={`type-card-title font-bold ${C.color.text}`}>Источник</h2>
      </header>
      <SourceBody lead={lead} />
    </section>
  );
}

function SourceBody({ lead }: { lead: LeadOut }) {
  const formName = lead.source_form_name;
  const formId = lead.source_form_id;
  const utm = lead.latest_utm ?? {};
  const utmEntries = Object.entries(utm).filter(([, v]) => v);

  // Pull source_domain + raw_payload from the latest form_submission
  // Activity. We read the feed instead of duplicating server-side
  // because the feed is already in TanStack Query cache by the time
  // the user opens this tab.
  const feed = useFeed(lead.id);
  const latestSubmission = feed.data?.pages
    ?.flatMap((p) => p.items)
    ?.find((it) => it.type === "form_submission");
  const sourceDomain =
    (latestSubmission?.payload_json?.source_domain as string | undefined) || null;
  const rawPayload = latestSubmission?.payload_json as Record<string, unknown> | undefined;

  return (
    <ul className="space-y-3 type-caption">
      <li className="flex items-start gap-3">
        <LinkIcon size={14} className="mt-0.5 text-brand-muted shrink-0" />
        <div className="flex-1 min-w-0">
          {formId && formName ? (
            <Link
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              href={`/leads-pool?form_id=${formId}` as any}
              className={`${C.color.accent} hover:underline`}
            >
              {formName}
            </Link>
          ) : (
            <span className={C.color.muted}>Форма удалена</span>
          )}
          {sourceDomain && (
            <p className={`${C.color.mutedLight} mt-0.5 break-all`}>
              {sourceDomain}
            </p>
          )}
        </div>
      </li>

      {utmEntries.length > 0 && (
        <li className="border-t border-brand-border pt-3">
          <p className={`${C.color.mutedLight} uppercase tracking-wide text-[10px] mb-2`}>
            UTM-параметры
          </p>
          <dl className="grid grid-cols-[120px_1fr] gap-y-1 gap-x-3 font-mono text-[11px]">
            {utmEntries.map(([k, v]) => (
              <>
                <dt key={`k-${k}`} className={C.color.muted}>
                  {k}
                </dt>
                <dd key={`v-${k}`} className={C.color.text}>
                  {String(v)}
                </dd>
              </>
            ))}
          </dl>
        </li>
      )}

      {rawPayload && (
        <li className="border-t border-brand-border pt-3">
          <RawPayloadDisclosure payload={rawPayload} />
        </li>
      )}
    </ul>
  );
}

function RawPayloadDisclosure({ payload }: { payload: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className="type-caption"
    >
      <summary className="cursor-pointer text-brand-muted inline-flex items-center gap-1 select-none">
        <ChevronDown
          size={12}
          className={`transition-transform ${open ? "rotate-0" : "-rotate-90"}`}
        />
        Raw payload
      </summary>
      <pre className="mt-2 p-2 bg-brand-panel rounded-md overflow-x-auto text-[10px] font-mono">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
```

### Step 5.2 — Render `<SourceSection>` in `DealAndAITab`

- [ ] Open `apps/web/components/lead-card/DealAndAITab.tsx`. At the top of the file (import block), add:

```typescript
import { SourceSection } from "./SourceSection";
```

- [ ] In the JSX, between «Card 2: Параметры сделки» and `<AIBriefCard ...>`, add:

```tsx
      {/* === Card 3: Источник (only for form-sourced leads) === */}
      <SourceSection lead={lead} />
```

(The existing AI Brief becomes Card 4 — comment label only, no logic change.)

### Step 5.3 — Add the chip in `LeadCard.tsx`

- [ ] Open `apps/web/components/lead-card/LeadCard.tsx`. Find the header area where company name is rendered. Add the chip immediately after the company name. The chip pattern:

```tsx
{lead.source_form_id && lead.source_form_name && (
  <Link
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    href={`/leads-pool?form_id=${lead.source_form_id}` as any}
    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-brand-soft text-brand-accent-text text-[11px] font-semibold hover:bg-brand-soft/80 transition-colors"
    title="Открыть пул лидов этого лендинга"
  >
    <Globe size={11} aria-hidden />
    Лендинг: {lead.source_form_name}
  </Link>
)}
{lead.source?.startsWith("form:") && !lead.source_form_name && (
  <span
    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-brand-panel text-brand-muted text-[11px] font-semibold"
    title="Форма удалена"
  >
    <Globe size={11} aria-hidden />
    Заявка с формы
  </span>
)}
```

- [ ] Ensure `Globe` is imported from `lucide-react` and `Link` from `next/link`.

### Step 5.4 — Build + visual verification

- [ ] Run: `cd apps/web && npm run typecheck && npm run lint && pnpm build`
- [ ] Expected: typecheck clean, lint baseline 21 warnings unchanged, build green.
- [ ] Open a form-sourced lead locally → expect chip in header and section in «Сделка и AI» tab.

### Step 5.5 — Commit

```bash
git add apps/web/components/lead-card/SourceSection.tsx apps/web/components/lead-card/LeadCard.tsx apps/web/components/lead-card/DealAndAITab.tsx
git commit -m "feat(lead-card): G5 — source chip + Источник section"
```

---

## Task 6 — Frontend: `/leads-pool` filter dropdown + per-row chip

**Files:**
- Modify: `apps/web/app/(app)/leads-pool/page.tsx`

### Step 6.1 — Find the filter bar

- [ ] Open `apps/web/app/(app)/leads-pool/page.tsx`. Locate the filter bar with `segment` / `city` dropdowns. The filter state lives at the top of the component as a `useState` or `useReducer` object.

### Step 6.2 — Add `form_id` to filter state

- [ ] Find the filter state definition and add `form_id?: string` to its type and `form_id: undefined` to its initial value.
- [ ] Pass `form_id: filters.form_id` into the `useLeads(...)` call.

### Step 6.3 — Add the dropdown

- [ ] Near the existing filter dropdowns, import `useForms` from `@/lib/hooks/use-forms`. Add:

```tsx
const formsQuery = useForms();
const forms = formsQuery.data?.items ?? [];
```

- [ ] Render the dropdown adjacent to «Сегмент» / «Город»:

```tsx
<select
  value={filters.form_id ?? ""}
  onChange={(e) =>
    setFilters((f) => ({
      ...f,
      form_id: e.target.value || undefined,
    }))
  }
  className="text-sm px-2 py-1.5 rounded-lg bg-canvas border border-black/5 outline-none focus:border-brand-accent"
>
  <option value="">Все источники</option>
  {forms
    .filter((f) => f.is_active)
    .map((f) => (
      <option key={f.id} value={f.id}>
        {f.name}
      </option>
    ))}
</select>
```

- [ ] Wire the `?form_id=` URL search-param to the filter state on mount so the chip-link from the Lead Card pre-selects the form. Use `useSearchParams()`:

```tsx
const search = useSearchParams();
const presetFormId = search.get("form_id") ?? undefined;
// In a `useEffect` that runs once: setFilters((f) => ({ ...f, form_id: presetFormId }));
```

### Step 6.4 — Add the per-row source chip

- [ ] Find the row render where company name appears. Add next to or below the company name:

```tsx
{lead.source_form_name && (
  <span
    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono text-brand-accent-text bg-brand-soft"
    title="Источник заявки"
  >
    <Globe size={9} aria-hidden />
    {lead.source_form_name}
  </span>
)}
```

- [ ] Ensure `Globe` is imported from `lucide-react`.

### Step 6.5 — Build + visual verification

- [ ] Run: `cd apps/web && npm run typecheck && pnpm build`
- [ ] Open `/leads-pool` locally → filter dropdown lists active forms; selecting one filters; per-row chip shows source for form-sourced rows.
- [ ] Click a Lead Card chip with `?form_id=` URL → returns to /leads-pool with that form pre-selected.

### Step 6.6 — Commit

```bash
git add apps/web/app/\(app\)/leads-pool/page.tsx
git commit -m "feat(leads-pool): G6 — Источник filter + per-row chip"
```

---

## Task 7 — Frontend: Globe icon on pipeline kanban card

**Files:**
- Modify: `apps/web/components/pipeline/PipelineLeadCard.tsx`

### Step 7.1 — Add the icon next to company name

- [ ] Open `apps/web/components/pipeline/PipelineLeadCard.tsx`. Locate the row where `lead.company_name` is rendered (row 1, top of the card).
- [ ] Add `Globe` to the `lucide-react` import.
- [ ] Render the icon inline next to the company name when `lead.source` starts with `form:`:

```tsx
{lead.source?.startsWith("form:") && (
  <Globe
    size={10}
    className="shrink-0 text-brand-accent-text"
    aria-hidden
  >
    <title>{lead.source_form_name ?? "Заявка с формы"}</title>
  </Globe>
)}
```

(If Tailwind / Lucide doesn't accept `<title>` as a child, wrap the icon in a `<span title={...}>`.)

### Step 7.2 — Build + visual verification

- [ ] Run: `cd apps/web && npm run typecheck && pnpm build`
- [ ] Visit `/pipeline` locally → form-sourced cards have a tiny Globe icon next to company name.

### Step 7.3 — Commit

```bash
git add apps/web/components/pipeline/PipelineLeadCard.tsx
git commit -m "feat(pipeline): G7 — Globe icon for form-sourced kanban cards"
```

---

## Task 8 — Frontend: `FormStatsCard` on `/forms` admin page

**Files:**
- Create: `apps/web/components/forms/FormStatsCard.tsx`
- Modify: `apps/web/app/(app)/forms/page.tsx`

### Step 8.1 — Create the stats card

- [ ] Create `apps/web/components/forms/FormStatsCard.tsx`:

```tsx
"use client";

import { Loader2 } from "lucide-react";
import { useFormStats } from "@/lib/hooks/use-forms";

interface Props {
  formId: string;
}

export function FormStatsCard({ formId }: Props) {
  const { data, isLoading, isError } = useFormStats(formId);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 mt-2 text-[11px] text-muted-3">
        <Loader2 size={11} className="animate-spin" />
        Загружаем статистику…
      </div>
    );
  }
  if (isError || !data) {
    return null; // silent — admin doesn't need an error toast per form
  }

  const total = data.submissions_30d;
  const past_first =
    total === 0
      ? 0
      : Math.round(
          ((total - (data.by_stage["Новый контакт"] ?? 0)) / total) * 100,
        );

  return (
    <div className="mt-2 flex items-center gap-3 flex-wrap text-[11px] font-mono text-muted-2">
      <Stat label="за 7 дней" value={data.submissions_7d} />
      <Stat label="за 30 дней" value={data.submissions_30d} />
      <Stat label="в работе" value={data.claimed_count} />
      {total > 0 && <Stat label="квалификация+" value={`${past_first}%`} />}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <span>
      <span className="text-ink font-semibold tabular-nums">{value}</span>{" "}
      <span className="opacity-70">{label}</span>
    </span>
  );
}
```

### Step 8.2 — Render in the forms page

- [ ] Open `apps/web/app/(app)/forms/page.tsx`. Import `FormStatsCard`:

```typescript
import { FormStatsCard } from "@/components/forms/FormStatsCard";
```

- [ ] In the list row render (where each form is displayed), add immediately after the form's name + slug metadata block:

```tsx
<FormStatsCard formId={form.id} />
```

### Step 8.3 — Build + visual verification

- [ ] Run: `cd apps/web && npm run typecheck && pnpm build`
- [ ] Open `/forms` locally as admin → each row shows the stat strip; zero-submission forms show «0 за 7 дней · 0 за 30 дней · 0 в работе» (quality % hidden).

### Step 8.4 — Commit

```bash
git add apps/web/components/forms/FormStatsCard.tsx apps/web/app/\(app\)/forms/page.tsx
git commit -m "feat(forms): G8 — per-form stats card on admin page"
```

---

## Task 9 — Docs: `docs/landings.md`

**Files:**
- Create: `docs/landings.md`

### Step 9.1 — Write the docs

- [ ] Create `docs/landings.md` with this content (full text — no placeholders):

```markdown
# Подключение лендингов к CRM

Документация для маркетолога / дизайнера, поднимающего лендинг в Claude
или v0. Минимум — 5 минут до рабочей формы и первой заявки в CRM.

## Что вы получите

- Одна форма на лендинге → одна заявка в CRM в **Базе лидов** через
  ~5 секунд.
- На карточке лида видно «🌐 Лендинг: <имя формы>» — клик ведёт в пул
  отфильтрованный по этому лендингу.
- Все UTM-параметры с URL фиксируются и показываются структурно.
- На странице «Формы» (admin/head) — сводка: заявки за 7д / 30д /
  взято в работу / конверсия дальше первого этапа.

## Шаг 1. Создать форму в CRM

1. Открыть `https://crm.drinkx.tech/forms` (нужны права admin или head).
2. Кнопка «Новая форма».
3. Заполнить:
   - **Имя** — как форма будет называться на карточке лида: «HoReCa
     МСК», «АЗС лендинг», «Калькулятор ROI».
   - **Slug** — короткий URL-safe идентификатор латиницей: `horeca-msk`,
     `azs-landing`, `roi-calc`. Slug **уникален глобально**, его
     потом не поменять.
   - **Поля** — минимум `phone` + `email`. Опционально `name`,
     `company_name`, `notes`. Имена полей не важны — backend знает
     RU/EN-синонимы (`phone`/`телефон`/`тел`; `email`/`почта`;
     `name`/`имя`; и т.д.), любое непонятное поле сохраняется в
     `raw_payload`.
   - **Целевая воронка / стадия** — куда падает лид. По умолчанию —
     первый этап «Новые клиенты».
4. Сохранить → скопировать slug.

## Шаг 2. Подключить форму на лендинг

Два паттерна. Выбирайте по технологии лендинга.

### Паттерн A1 — статический HTML с embed.js

Подходит для лендингов, сгенерированных Claude в виде одного `index.html`,
или для любых не-React сайтов где можно вставить `<script>` в `<head>` /
`<body>`.

```html
<!-- В <body> там, где должна появиться форма: -->
<div id="drinkx-form"></div>

<!-- В <head> или прямо после <div>: -->
<script
  async
  src="https://crm.drinkx.tech/api/public/forms/horeca-msk/embed.js"
></script>
```

Замените `horeca-msk` на ваш slug. Скрипт самодостаточный (без зависимостей),
рендерит форму внутрь `<div id="drinkx-form">`. Стилизация — наша
дефолтная; если нужен полный контроль над дизайном, используйте паттерн A2.

### Паттерн A2 — React / Next.js (v0 / Claude-generated)

Подходит для лендингов на React/Next.js. Скопируйте компонент ниже к
себе на лендинг. Стилизуйте Tailwind-классами как угодно — UI ваш, контракт
с CRM единственный: один POST на `/api/public/forms/{slug}/submit`.

```tsx
"use client";

import { useEffect, useState, type FormEvent } from "react";

const SLUG = "horeca-msk"; // ← подставьте свой slug
const ENDPOINT = `https://crm.drinkx.tech/api/public/forms/${SLUG}/submit`;
const UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_content",
  "utm_term",
];

export function LeadForm() {
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [utm, setUtm] = useState<Record<string, string>>({});
  const [state, setState] = useState<"idle" | "sending" | "ok" | "error">("idle");

  // Read UTM params from the landing URL once on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const collected: Record<string, string> = {};
    for (const key of UTM_KEYS) {
      const value = params.get(key);
      if (value) collected[key] = value;
    }
    setUtm(collected);
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setState("sending");
    try {
      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, email, name, utm }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setState("ok");
    } catch {
      setState("error");
    }
  }

  if (state === "ok") {
    return (
      <div className="p-6 bg-emerald-50 text-emerald-900 rounded-2xl">
        Спасибо! Мы свяжемся с вами в ближайшее время.
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3 max-w-md">
      <input
        type="tel"
        required
        placeholder="Телефон"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        className="px-4 py-2 rounded-xl border border-neutral-300"
      />
      <input
        type="email"
        required
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="px-4 py-2 rounded-xl border border-neutral-300"
      />
      <input
        type="text"
        placeholder="Имя (необязательно)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="px-4 py-2 rounded-xl border border-neutral-300"
      />
      <button
        type="submit"
        disabled={state === "sending"}
        className="px-4 py-2 rounded-xl bg-[#FF4E00] text-white font-semibold disabled:opacity-50"
      >
        {state === "sending" ? "Отправляем…" : "Получить предложение"}
      </button>
      {state === "error" && (
        <p className="text-rose-600 text-sm">
          Не удалось отправить. Попробуйте ещё раз через минуту.
        </p>
      )}
    </form>
  );
}
```

## Шаг 3. Тестовый прогон

1. Откройте лендинг в браузере, заполните и отправьте форму.
2. В CRM откройте `/leads-pool`, отфильтруйте по своей форме («Источник»
   → имя вашей формы). Лид появится за ~5 секунд.
3. Откройте лид → в шапке должен быть чип «🌐 Лендинг: <имя>».
4. На вкладке «Сделка и AI» — карточка «Источник» с form_name +
   source_domain + UTM-таблицей.
5. На `/forms` рядом с вашей формой — счётчик «1 за 7 дней».

Прогоните ещё раз с UTM в URL, например:
`?utm_source=test&utm_campaign=smoke&utm_medium=manual`.
Переоткройте новый лид → UTM-таблица должна отразить эти значения.

## CORS и rate-limits

- Endpoint `https://crm.drinkx.tech/api/public/forms/*` — wildcard-CORS
  (по дизайну, любые origins). Allowlist не нужен.
- Rate-limit: per `(slug, IP)`, защищает от ботов. Нормальные пользователи
  не упрутся.

## Что НЕ нужно делать

- Не нужно подключать никаких SDK / npm-пакетов. Один endpoint, чистый POST.
- Не нужно ставить captcha — rate-limit + AI-фильтрация в Inbox
  закрывают спам.
- Не нужно хранить slug в `.env` — он публичный по своей природе
  (видно в исходниках лендинга всё равно).

## Когда нужна помощь

- Лид не приходит → проверьте Network tab в браузере. POST должен
  вернуть `200`. Если `404` — slug опечатан или форма выключена.
- Лид приходит без UTM → проверьте что URL лендинга открыт с UTM-параметрами.
  UTM читаются с `window.location.search` на момент монтирования формы.
- Лид приходит, но имя формы пустое (`📥 Заявка с формы`) → форму
  удалили в админке, а старый embed на лендинге продолжает работать.
  Создайте форму заново или замените slug.
```

### Step 9.2 — Commit

```bash
git add docs/landings.md
git commit -m "docs: G9 — landings.md self-coded integration guide"
```

---

## Task 10 — Smoke verification on staging / local

**Files:** none (manual verification)

### Step 10.1 — Run the test form end-to-end

- [ ] Create a form in `/forms` with slug `smoke-test-3-6`, fields `phone` + `email`.
- [ ] Copy the embed snippet into `~/Desktop/smoke-3-6.html`:

```html
<!doctype html>
<html><body>
<div id="drinkx-form"></div>
<script src="https://crm.drinkx.tech/api/public/forms/smoke-test-3-6/embed.js"></script>
</body></html>
```

- [ ] Open it in a browser, submit fake data.
- [ ] `/leads-pool` filtered by «smoke-test-3-6» → new lead visible.
- [ ] Open the lead → chip in header, «Источник» section visible in DealAndAITab.
- [ ] `/pipeline` → the new lead's card has a Globe icon next to company name.
- [ ] `/forms` → smoke-test-3-6 row shows «1 заявка за 7 дней».
- [ ] Re-submit with `?utm_source=smoke&utm_campaign=test` in the URL → reopen the new lead → UTM table shows both keys.

### Step 10.2 — Update the sprint spec checklist

- [ ] Open `docs/SPRINT_3_6_LANDING_FORMS_ATTRIBUTION.md` → smoke checklist section → tick the boxes you verified.

### Step 10.3 — Commit the smoke checklist update

```bash
git add docs/SPRINT_3_6_LANDING_FORMS_ATTRIBUTION.md
git commit -m "docs(sprint-3.6): smoke run verified"
```

---

## Final — PR

### Step F.1 — Push the branch

```bash
git push -u origin sprint/3.6-landing-forms-attribution
```

### Step F.2 — Open the PR

```bash
gh pr create --title "Sprint 3.6 — Landing Forms Attribution" --body "..."
```

PR description should follow the Sprint 3.5 pattern: summary, gate-by-gate
recap, test plan checklist.

---

## Self-review notes (carried out 2026-05-18)

- **Spec coverage:** G1–G4 of the spec map to Tasks 1–9 here. G2's
  «по-row chip» and «pipeline Globe icon» are Tasks 6 + 7. Smoke
  checklist from the spec is Task 10.
- **Placeholder scan:** No TBDs. Code blocks complete in every step.
  Test code is concrete; service code is concrete.
- **Type consistency:** `source_form_id`, `source_form_name`,
  `latest_utm`, `FormStatsOut` are used consistently across backend
  schema, frontend types, hooks, and components.
- **Out-of-scope adherence:** No Tilda/Webflow integration tasks.
  No dashboard tasks. No UTM normalization.
