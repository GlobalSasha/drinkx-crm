# base_update — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `apps/api/app/base_update` domain that lets admin/head upload a batch of `.md` ЛПР cards, has the LLM extract structured company/contacts/brief, dedups + matches against the base, auto-writes the safe parts (new leads land in the pool with `needs_review`), and holds the disputable parts as per-type conflicts an admin resolves one-by-one — surfaced through a new Settings section.

**Architecture:** Three-table job model (`IngestJob 1—N IngestRecord 1—N IngestConflict`), all workspace-scoped. Two Celery phases — `extract_and_match` (LLM extract → batch dedup → DB match → auto-apply safe → status `ready`) and `apply_resolutions` (apply admin decisions → `done`). Reuses `enrichment` LLM fallback + budget, `companies.utils.normalize_company_name`, and the `companies/leads/contacts` services. REST under `/api/base-update/*`, polled by the frontend like the existing import/export jobs.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async, `Mapped`), Alembic, Celery (broker = Upstash Redis), Pydantic v2 (permissive AI schemas), Next.js 15 + TanStack Query + shadcn/Tailwind brand tokens.

**Spec:** `docs/superpowers/specs/2026-05-21-base-update-design.md` (approved). Read it before starting.

**Branch:** `feat/base-update` (off `main`). The earlier `feat/base-update-spec` branch is superseded by this one — delete it after merge.

---

## Conventions baked in (do not deviate)

1. **Celery `@task` wrappers live in `apps/api/app/scheduled/jobs.py`**, NOT in the domain. The domain exports an async core; `jobs.py` wraps it with the `_build_task_engine_and_factory()` NullPool pattern + `asyncio.run`.
2. **Register `app.base_update.models` as a side-effect import in BOTH** `apps/api/app/scheduled/celery_app.py` (the `include`/import block, ~lines 18–32) and `apps/api/app/alembic/env.py` (~lines 15–30). Skipping either → `failed to locate a name` in the worker / empty autogenerate.
3. **`complete_with_fallback(..., db=, workspace_id=)` records `llm_usage` itself.** Never record manually. Wrap calls with `has_budget_remaining` (pre) and `add_to_daily_spend` (post, best-effort try/except).
4. **Pool leads with review are built directly** as `Lead(..., assignment_status="pool", needs_review=True, source="base_update", ai_data={...})` — NOT via `leads.services.create_lead` (which assigns to a user). Resolve first stage via `pipelines.repositories.get_default_first_stage`.
5. **Async REST returns `status_code=status.HTTP_202_ACCEPTED`**; dispatch via `celery_app.send_task(name, args=[str(id)])` after `await db.commit()`; client polls with `refetchInterval` keyed off the `status` string.
6. **Admin/head guard:** `user: Annotated[User, Depends(require_admin_or_head)]` from `app.auth.dependencies`.
7. **Never raise on LLM output.** All extraction Pydantic models use `Optional` + defaults and a permissive `field_validator(mode="before")`.
8. Run backend checks per touched module: `cd apps/api && uv run python -m py_compile <file>` and `uv run pytest <test> -v`. Migrations: `make db.migrate`.

---

## File Structure

### Backend — `apps/api/app/base_update/` (new package)
- `__init__.py` — empty package marker.
- `models.py` — `IngestJob`, `IngestRecord`, `IngestConflict` ORM models.
- `schemas.py` — **AI extraction** Pydantic models (`ExtractedContact`, `ExtractedCompany`, `ExtractedCard`) — permissive, never raise.
- `api_schemas.py` — **REST DTOs** (`IngestJobOut`, `IngestRecordOut`, `IngestConflictOut`, `ResolveConflictIn`, `JobStatsOut`) with `from_attributes`.
- `extractor.py` — prompt builder + `extract_card(md_text, *, db, workspace_id) -> ExtractedCard` wrapping `complete_with_fallback`.
- `dedup.py` — pure batch-dedup (#6): group `ExtractedCard[]` by normalized name, merge or flag.
- `matcher.py` — pure DB-matching helpers: company match (0/1/>1), lead-target choice (#4), contact match (#3), field diff classification (#2/#5).
- `services.py` — job CRUD, conflict listing/resolution persistence, the auto-apply writer, the resolution applier. Calls `companies/leads/contacts` services.
- `orchestrator.py` — async cores `run_extract_and_match(db, job_id)` and `run_apply_resolutions(db, job_id)`.
- `routers.py` — `APIRouter(prefix="/api/base-update", tags=["base_update"])`.
- `constants.py` — enums-as-constants: statuses, conflict types, target kinds, resolutions, the field whitelist.

### Backend — modified
- `apps/api/app/enrichment/providers/base.py` — add `TaskType.lpr_extraction` (+ to `_FLASH_TASKS`).
- `apps/api/app/scheduled/jobs.py` — two `@celery_app.task` wrappers.
- `apps/api/app/scheduled/celery_app.py` — side-effect import of base_update models.
- `apps/api/app/alembic/env.py` — side-effect import of base_update models.
- `apps/api/app/main.py` — `app.include_router(base_update_router)`.
- `apps/api/alembic/versions/20260522_0036_base_update_tables.py` — new migration.

### Backend — tests `apps/api/tests/base_update/`
- `test_schemas.py`, `test_dedup.py`, `test_matcher.py`, `test_services_apply.py`, `test_api_integration.py`.
- Fixtures: real `.md` cards copied into `apps/api/tests/base_update/fixtures/` from `~/Desktop/DrinkX_Retail_LPR` / `DrinkX_AZS_LPR`.

### Frontend — `apps/web`
- `lib/types.ts` — add `IngestJobOut`, `IngestRecordOut`, `IngestConflictOut` types.
- `lib/hooks/use-base-update.ts` — upload (raw `fetch` multipart), poll job, list conflicts, resolve, apply.
- `components/settings/BaseUpdateSection.tsx` — upload dropzone + progress + stats summary + conflict list mount.
- `components/settings/base-update/ConflictCard.tsx` — one conflict, per-type resolution buttons.
- `app/(app)/settings/page.tsx` — register the new section.

---

## Phase 0 — Scaffolding & data model

### Task 1: Constants module

**Files:**
- Create: `apps/api/app/base_update/__init__.py` (empty)
- Create: `apps/api/app/base_update/constants.py`

- [ ] **Step 1: Create the empty package marker**

```bash
mkdir -p apps/api/app/base_update
touch apps/api/app/base_update/__init__.py
```

- [ ] **Step 2: Write constants**

```python
# apps/api/app/base_update/constants.py
"""String enums (as module constants) for the base_update domain.

Kept as plain strings (not Python Enum) so they serialise directly to
JSON columns / Pydantic without `.value` ceremony, matching the
import_export domain's status-string convention.
"""

# IngestJob.status lifecycle
JOB_PENDING = "pending"
JOB_EXTRACTING = "extracting"
JOB_MATCHING = "matching"
JOB_READY = "ready"        # auto-applied; conflicts await resolution
JOB_RESOLVING = "resolving"
JOB_DONE = "done"
JOB_FAILED = "failed"

# IngestRecord.action
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_CONFLICT = "conflict"
ACTION_SKIPPED = "skipped"

# IngestConflict.type (the 6 conflict kinds from the spec)
C_COMPANY_AMBIGUOUS = "company_ambiguous"   # #1
C_FIELD_MISMATCH = "field_mismatch"         # #2
C_CONTACT_MISMATCH = "contact_mismatch"     # #3
C_LEAD_TARGET = "lead_target"               # #4
C_LOW_CONFIDENCE = "low_confidence"         # #5
C_BATCH_DUPLICATE = "batch_duplicate"       # #6

# IngestConflict.target_kind
TK_COMPANY = "company"
TK_LEAD = "lead"
TK_CONTACT = "contact"
TK_BRIEF = "brief"

# IngestConflict.status
CONFLICT_OPEN = "open"
CONFLICT_RESOLVED = "resolved"
CONFLICT_SKIPPED = "skipped"

# IngestConflict.resolution (admin's decision)
R_KEEP = "keep"                 # keep base value
R_OVERWRITE = "overwrite"       # take incoming value
R_MANUAL = "manual"             # use resolved_value
R_ADD_SEPARATE = "add_separate" # add as a new contact/lead
R_PICK = "pick"                 # pick a candidate (resolved_value = id)
R_SKIP = "skip"

# Fields eligible for auto-fill / #2 conflicts (company + lead level)
DIFFABLE_FIELDS = ("segment", "priority", "website", "inn", "city", "email", "phone")

# #5 trigger: extraction_confidence below this is held for review
MIN_EXTRACTION_CONFIDENCE = 0.55
```

- [ ] **Step 3: Verify it imports**

Run: `cd apps/api && uv run python -c "from app.base_update import constants as c; print(c.JOB_READY, c.DIFFABLE_FIELDS)"`
Expected: prints `ready ('segment', 'priority', ...)`

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/base_update/__init__.py apps/api/app/base_update/constants.py
git commit -m "feat(base_update): domain package + constants"
```

---

### Task 2: ORM models

**Files:**
- Create: `apps/api/app/base_update/models.py`

- [ ] **Step 1: Write the models**

```python
# apps/api/app/base_update/models.py
"""ORM models for the base_update domain.

IngestJob 1—N IngestRecord 1—N IngestConflict. All workspace-scoped,
FK cascade. Mirrors the import_export job/status-string convention.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_update import constants as c
from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class IngestJob(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "ingest_jobs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=c.JOB_PENDING, index=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_filenames: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    stats_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    records: Mapped[list["IngestRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class IngestRecord(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "ingest_records"

    ingest_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    extracted_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    match_company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    match_lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_files: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["IngestJob"] = relationship(back_populates="records")
    conflicts: Mapped[list["IngestConflict"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class IngestConflict(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "ingest_conflicts"

    ingest_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingest_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    base_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    incoming_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidates_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=c.CONFLICT_OPEN, index=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # see step 2 note

    record: Mapped["IngestRecord"] = relationship(back_populates="conflicts")
```

- [ ] **Step 2: Fix the `resolved_at` type**

`resolved_at` must be a timestamp, not UUID. Edit it to:

```python
    from datetime import datetime  # add to imports at top
    from sqlalchemy import DateTime
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

(Place the `datetime` / `DateTime` imports with the other top-of-file imports.)

- [ ] **Step 3: Register models for the mapper registry (both lists)**

In `apps/api/app/scheduled/celery_app.py`, add to the side-effect import block (~lines 18–32):
```python
from app.base_update import models as _base_update_models  # noqa: F401
```
In `apps/api/app/alembic/env.py`, add to its side-effect import block (~lines 15–30):
```python
from app.base_update import models as _base_update_models  # noqa: F401
```

- [ ] **Step 4: Verify import + mapper config**

Run: `cd apps/api && uv run python -c "from app.base_update import models; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('ok', models.IngestJob.__tablename__)"`
Expected: prints `ok ingest_jobs` with no mapper errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/base_update/models.py apps/api/app/scheduled/celery_app.py apps/api/app/alembic/env.py
git commit -m "feat(base_update): ORM models (IngestJob/Record/Conflict) + mapper registration"
```

---

### Task 3: Alembic migration

**Files:**
- Create: `apps/api/alembic/versions/20260522_0036_base_update_tables.py`

- [ ] **Step 1: Autogenerate the migration**

Run: `cd apps/api && uv run alembic revision --autogenerate -m "base_update tables"`
Then rename the generated file to `20260522_0036_base_update_tables.py` and set inside it:
```python
revision = "0036_base_update_tables"
down_revision = "0035_lead_notes_table"
```

- [ ] **Step 2: Verify the autogenerated body** creates `ingest_jobs`, `ingest_records`, `ingest_conflicts` with the FK `ondelete` rules and the indexes (`ix_ingest_*_workspace_id` / `_ingest_job_id` / `_status` / `_normalized_name`). If autogenerate missed an index, add explicit `op.create_index(...)` lines mirroring `20260521_0035_lead_notes_table.py`.

- [ ] **Step 3: Apply + verify round-trip**

Run: `make db.migrate` (→ `alembic upgrade head`)
Then: `cd apps/api && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: upgrade/downgrade/upgrade all succeed; tables exist.

- [ ] **Step 4: Commit**

```bash
git add apps/api/alembic/versions/20260522_0036_base_update_tables.py
git commit -m "feat(base_update): migration 0036 — ingest tables"
```

---

## Phase 1 — AI extraction (pure logic first)

### Task 4: ExtractedCard schema (permissive, never raises)

**Files:**
- Create: `apps/api/app/base_update/schemas.py`
- Test: `apps/api/tests/base_update/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/base_update/test_schemas.py
from app.base_update.schemas import ExtractedCard


def test_empty_dict_yields_defaults_and_does_not_raise():
    card = ExtractedCard.model_validate({})
    assert card.company.name == ""
    assert card.contacts == []
    assert card.ai_brief == ""
    assert card.extraction_confidence == 0.0


def test_garbage_contact_is_coerced_not_raised():
    card = ExtractedCard.model_validate(
        {"company": {"name": "ООО Ромашка"}, "contacts": ["not-a-dict", {"name": "Иван"}]}
    )
    # the string contact is dropped; the dict one survives
    assert [ctc.name for ctc in card.contacts] == ["Иван"]


def test_role_type_outside_canon_falls_back_to_null():
    card = ExtractedCard.model_validate(
        {"company": {"name": "X"}, "contacts": [{"name": "A", "role_type": "ceo-supreme"}]}
    )
    assert card.contacts[0].role_type is None


def test_confidence_clamped_to_unit_interval():
    assert ExtractedCard.model_validate({"extraction_confidence": 5}).extraction_confidence == 1.0
    assert ExtractedCard.model_validate({"extraction_confidence": -2}).extraction_confidence == 0.0
```

- [ ] **Step 2: Run it to confirm failure**

Run: `cd apps/api && uv run pytest tests/base_update/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: app.base_update.schemas`.

- [ ] **Step 3: Write the schema**

```python
# apps/api/app/base_update/schemas.py
"""AI-extraction Pydantic models. Permissive by design — these wrap raw
LLM output and MUST NOT raise on missing/garbage fields (PRD §7.2)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

CANON_ROLES = {"economic_buyer", "champion", "technical_buyer", "operational_buyer"}
CANON_PRIORITY = {"A", "B", "C", "D"}


class ExtractedContact(BaseModel):
    name: str = ""
    title: str | None = None
    role_type: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    linkedin: str | None = None
    source: str | None = None
    confidence: float = 0.0

    @field_validator("role_type", mode="before")
    @classmethod
    def _canon_role(cls, v):
        return v if v in CANON_ROLES else None


class ExtractedCompany(BaseModel):
    name: str = ""
    segment: str | None = None
    priority: str | None = None
    website: str | None = None
    inn: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def _canon_priority(cls, v):
        s = str(v).strip().upper() if v is not None else None
        return s if s in CANON_PRIORITY else None


class ExtractedCard(BaseModel):
    company: ExtractedCompany = Field(default_factory=ExtractedCompany)
    contacts: list[ExtractedContact] = Field(default_factory=list)
    ai_brief: str = ""
    extraction_confidence: float = 0.0

    @field_validator("contacts", mode="before")
    @classmethod
    def _drop_non_dicts(cls, v):
        if not isinstance(v, list):
            return []
        return [x for x in v if isinstance(x, dict)]

    @field_validator("company", mode="before")
    @classmethod
    def _company_default(cls, v):
        return v if isinstance(v, dict) else {}

    @field_validator("extraction_confidence", mode="before")
    @classmethod
    def _clamp(cls, v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd apps/api && uv run pytest tests/base_update/test_schemas.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/base_update/schemas.py apps/api/tests/base_update/test_schemas.py
git commit -m "feat(base_update): permissive ExtractedCard schema + tests"
```

---

### Task 5: Extractor (LLM wrapper)

**Files:**
- Modify: `apps/api/app/enrichment/providers/base.py` (add `TaskType.lpr_extraction`)
- Create: `apps/api/app/base_update/extractor.py`
- Test: `apps/api/tests/base_update/test_extractor.py`

- [ ] **Step 1: Add the TaskType member**

In `apps/api/app/enrichment/providers/base.py`, add to the `TaskType` enum:
```python
    lpr_extraction = "lpr_extraction"
```
and include it in `_FLASH_TASKS` (cheap/fast extraction):
```python
_FLASH_TASKS = {TaskType.research_synthesis, TaskType.daily_plan, TaskType.prefilter, TaskType.lpr_extraction}
```

- [ ] **Step 2: Write the failing test (LLM mocked)**

```python
# apps/api/tests/base_update/test_extractor.py
import json
from types import SimpleNamespace

import pytest

from app.base_update import extractor
from app.base_update.schemas import ExtractedCard


@pytest.mark.asyncio
async def test_extract_card_parses_llm_json(monkeypatch):
    payload = {
        "company": {"name": "ООО Ромашка", "city": "Москва", "priority": "A"},
        "contacts": [{"name": "Иван Петров", "title": "Директор", "role_type": "economic_buyer"}],
        "ai_brief": "Сеть кофеен, 12 точек.",
        "extraction_confidence": 0.82,
    }

    async def fake_complete(**kwargs):
        return SimpleNamespace(text=json.dumps(payload), cost_usd=0.0)

    monkeypatch.setattr(extractor, "complete_with_fallback", fake_complete)
    card = await extractor.extract_card("# Ромашка\n...", db=None, workspace_id=None)
    assert isinstance(card, ExtractedCard)
    assert card.company.name == "ООО Ромашка"
    assert card.contacts[0].role_type == "economic_buyer"
    assert card.extraction_confidence == 0.82


@pytest.mark.asyncio
async def test_extract_card_survives_non_json(monkeypatch):
    async def fake_complete(**kwargs):
        return SimpleNamespace(text="sorry I cannot", cost_usd=0.0)

    monkeypatch.setattr(extractor, "complete_with_fallback", fake_complete)
    card = await extractor.extract_card("garbage", db=None, workspace_id=None)
    assert card.company.name == ""        # falls back to empty, never raises
    assert card.extraction_confidence == 0.0
```

- [ ] **Step 3: Run to confirm failure**

Run: `cd apps/api && uv run pytest tests/base_update/test_extractor.py -v`
Expected: FAIL — `app.base_update.extractor` missing.

- [ ] **Step 4: Write the extractor**

```python
# apps/api/app/base_update/extractor.py
"""LLM extraction of a single .md ЛПР card → ExtractedCard."""
from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.base_update.schemas import ExtractedCard
from app.enrichment.providers.base import TaskType
from app.enrichment.providers.factory import complete_with_fallback

_SYSTEM = (
    "Ты извлекаешь структуру из русской markdown-карточки ЛПР для B2B-CRM. "
    "Верни СТРОГО JSON по схеме {company, contacts[], ai_brief, extraction_confidence}. "
    "company: name (обяз.), segment, priority (A/B/C/D), website, inn, city, phone, email. "
    "contacts[]: name, title, role_type, email, phone, telegram, linkedin, source, confidence. "
    "role_type МАППИТСЯ в один из: economic_buyer (держит бюджет/решение), "
    "champion (продвигает внутри), technical_buyer (технические требования), "
    "operational_buyer (эксплуатация/закупка операционная). "
    "ai_brief: 2-4 предложения — описание, масштаб, кофейный сервис, триггеры, маршрут. "
    "Чего нет — null, НИЧЕГО НЕ ВЫДУМЫВАЙ. extraction_confidence: 0..1."
)


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


async def extract_card(
    md_text: str, *, db: AsyncSession | None, workspace_id: uuid.UUID | None
) -> ExtractedCard:
    completion = await complete_with_fallback(
        system=_SYSTEM,
        user=md_text[:12000],
        task_type=TaskType.lpr_extraction,
        max_tokens=1500,
        temperature=0.2,
        db=db,
        workspace_id=workspace_id,
    )
    try:
        data = json.loads(_strip_code_fence(completion.text))
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, ValueError):
        data = {}
    return ExtractedCard.model_validate(data)
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `cd apps/api && uv run pytest tests/base_update/test_extractor.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/enrichment/providers/base.py apps/api/app/base_update/extractor.py apps/api/tests/base_update/test_extractor.py
git commit -m "feat(base_update): LLM extractor + TaskType.lpr_extraction"
```

---

## Phase 2 — Dedup / matching / diff (pure, heavily TDD'd — the heart)

### Task 6: Batch dedup (#6)

**Files:**
- Create: `apps/api/app/base_update/dedup.py`
- Test: `apps/api/tests/base_update/test_dedup.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/base_update/test_dedup.py
from app.base_update.dedup import dedup_batch
from app.base_update.schemas import ExtractedCard


def _card(name, city=None, files=None, brief=""):
    c = ExtractedCard.model_validate({"company": {"name": name, "city": city}, "ai_brief": brief})
    return c, (files or [f"{name}.md"])


def test_same_normalized_name_merges_silently():
    groups = dedup_batch([
        _card("ООО Газпромнефть", city="Москва", files=["a.md"]),
        _card('Газпромнефть', city="Москва", files=["b.md"]),
    ])
    assert len(groups) == 1
    g = groups[0]
    assert sorted(g.source_files) == ["a.md", "b.md"]
    assert g.conflict is False


def test_same_name_diverging_field_flags_conflict():
    groups = dedup_batch([
        _card("Лукойл", city="Москва", files=["a.md"]),
        _card("Лукойл", city="Пермь", files=["b.md"]),
    ])
    assert len(groups) == 1
    assert groups[0].conflict is True
    assert groups[0].conflict_field == "city"


def test_distinct_companies_stay_separate():
    groups = dedup_batch([_card("Дикси"), _card("Перекрёсток")])
    assert len(groups) == 2
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd apps/api && uv run pytest tests/base_update/test_dedup.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write dedup**

```python
# apps/api/app/base_update/dedup.py
"""Batch dedup (#6): group extracted cards that refer to the same company.

Pure function — no DB. Grouping key is companies.utils.normalize_company_name.
Cards in a group whose scalar company fields diverge are flagged as a #6
conflict for the admin; otherwise the group is merged silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.base_update.schemas import ExtractedCard
from app.companies.utils import normalize_company_name

_MERGE_FIELDS = ("segment", "priority", "website", "inn", "city", "phone", "email")


@dataclass
class DedupGroup:
    normalized_name: str
    cards: list[ExtractedCard]
    source_files: list[str] = field(default_factory=list)
    conflict: bool = False
    conflict_field: str | None = None

    @property
    def primary(self) -> ExtractedCard:
        # the card with the most non-empty fields wins as the merge base
        return max(self.cards, key=_field_count)


def _field_count(card: ExtractedCard) -> int:
    return sum(1 for f in _MERGE_FIELDS if getattr(card.company, f))


def dedup_batch(items: list[tuple[ExtractedCard, list[str]]]) -> list[DedupGroup]:
    by_key: dict[str, DedupGroup] = {}
    for card, files in items:
        key = normalize_company_name(card.company.name or "")
        grp = by_key.get(key)
        if grp is None:
            grp = DedupGroup(normalized_name=key, cards=[], source_files=[])
            by_key[key] = grp
        grp.cards.append(card)
        for f in files:
            if f not in grp.source_files:
                grp.source_files.append(f)
    for grp in by_key.values():
        if len(grp.cards) > 1:
            _flag_divergence(grp)
    return list(by_key.values())


def _flag_divergence(grp: DedupGroup) -> None:
    for f in _MERGE_FIELDS:
        seen = {str(getattr(c.company, f)) for c in grp.cards if getattr(c.company, f)}
        if len(seen) > 1:
            grp.conflict = True
            grp.conflict_field = f
            return
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd apps/api && uv run pytest tests/base_update/test_dedup.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/base_update/dedup.py apps/api/tests/base_update/test_dedup.py
git commit -m "feat(base_update): batch dedup (#6) + tests"
```

---

### Task 7: Field-diff & contact-match classification (#2/#3/#5)

**Files:**
- Create: `apps/api/app/base_update/matcher.py`
- Test: `apps/api/tests/base_update/test_matcher.py`

These are pure functions over plain dicts (so they're trivially testable without ORM). The orchestrator passes in the relevant base values as dicts.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/base_update/test_matcher.py
from app.base_update import constants as c
from app.base_update.matcher import (
    classify_field,
    match_contact,
    is_low_confidence,
)


def test_classify_field_empty_base_autofills():
    assert classify_field(base=None, incoming="Москва") == "autofill"


def test_classify_field_equal_is_noop():
    assert classify_field(base="Москва", incoming="москва ") == "noop"


def test_classify_field_diverging_is_conflict():
    assert classify_field(base="Москва", incoming="Пермь") == "conflict"


def test_classify_field_empty_incoming_is_noop():
    assert classify_field(base="Москва", incoming=None) == "noop"


def test_match_contact_by_normalized_name():
    base = [{"id": "x", "name": "Иван Петров"}]
    assert match_contact(base, "иван  петров") == "x"
    assert match_contact(base, "Пётр Иванов") is None


def test_is_low_confidence():
    assert is_low_confidence(0.3, company_name="X") is True   # below threshold
    assert is_low_confidence(0.9, company_name="") is True    # empty name
    assert is_low_confidence(0.9, company_name="X") is False
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd apps/api && uv run pytest tests/base_update/test_matcher.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write matcher**

```python
# apps/api/app/base_update/matcher.py
"""Pure classification helpers for matching extracted data against the base.

DB lookups happen in services.py; these functions take plain values/dicts
so they're unit-testable without a session.
"""
from __future__ import annotations

from app.base_update.constants import MIN_EXTRACTION_CONFIDENCE
from app.companies.utils import normalize_company_name


def _norm(v) -> str:
    return str(v).strip().lower() if v is not None else ""


def classify_field(*, base, incoming) -> str:
    """Return 'autofill' | 'noop' | 'conflict' for one field (#2)."""
    if incoming is None or _norm(incoming) == "":
        return "noop"
    if base is None or _norm(base) == "":
        return "autofill"
    if _norm(base) == _norm(incoming):
        return "noop"
    return "conflict"


def match_contact(base_contacts: list[dict], incoming_name: str) -> str | None:
    """Return the id of a base contact whose normalized name matches, else None (#3)."""
    target = " ".join(_norm(incoming_name).split())
    for ctc in base_contacts:
        if " ".join(_norm(ctc.get("name")).split()) == target and target:
            return str(ctc.get("id"))
    return None


def is_low_confidence(extraction_confidence: float, *, company_name: str) -> bool:
    """#5 trigger."""
    if not (company_name or "").strip():
        return True
    return extraction_confidence < MIN_EXTRACTION_CONFIDENCE


def normalized_company_key(name: str) -> str:
    return normalize_company_name(name or "")
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd apps/api && uv run pytest tests/base_update/test_matcher.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/base_update/matcher.py apps/api/tests/base_update/test_matcher.py
git commit -m "feat(base_update): field-diff + contact-match + low-confidence classification"
```

---

## Phase 3 — Services: company match, auto-apply, resolution apply

### Task 8: Company/lead DB matching (services)

**Files:**
- Create: `apps/api/app/base_update/services.py` (first slice — read-side matching)
- Test: `apps/api/tests/base_update/test_services_match.py`

This slice queries the base. It needs the DB. Use the project's async test-session fixture (look at an existing `apps/api/tests/conftest.py` fixture — reuse the same `db`/`session` fixture name used by other domain tests; do NOT invent a new one).

- [ ] **Step 1: Inspect the existing test session fixture**

Run: `cd apps/api && sed -n '1,80p' tests/conftest.py`
Note the async session fixture name + how a workspace/user is seeded (reuse it verbatim in the test below; replace `session`/`seed_workspace` with the real names if different).

- [ ] **Step 2: Write the failing test**

```python
# apps/api/tests/base_update/test_services_match.py
import pytest

from app.base_update.services import match_company


@pytest.mark.asyncio
async def test_no_company_match_returns_create(session, seed_workspace):
    ws = seed_workspace
    result = await match_company(session, workspace_id=ws.id, name="Несуществующая Компания")
    assert result.action == "create"
    assert result.company_id is None


@pytest.mark.asyncio
async def test_single_exact_match_returns_update(session, seed_workspace, make_company):
    ws = seed_workspace
    comp = await make_company(workspace_id=ws.id, name="ООО Ромашка")
    result = await match_company(session, workspace_id=ws.id, name="Ромашка")
    assert result.action == "update"
    assert result.company_id == comp.id
```

- [ ] **Step 3: Run to confirm failure**

Run: `cd apps/api && uv run pytest tests/base_update/test_services_match.py -v`
Expected: FAIL — `match_company` missing (or fixture name mismatch — fix the fixture names first).

- [ ] **Step 4: Implement `match_company`**

```python
# apps/api/app/base_update/services.py  (initial)
"""base_update services: matching, auto-apply, resolution apply."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.companies.utils import normalize_company_name


@dataclass
class CompanyMatch:
    action: str  # "create" | "update" | "ambiguous"
    company_id: uuid.UUID | None
    candidates: list[dict]  # [{id, name}] for ambiguous (#1)


async def match_company(db: AsyncSession, *, workspace_id: uuid.UUID, name: str) -> CompanyMatch:
    key = normalize_company_name(name or "")
    if not key:
        return CompanyMatch(action="create", company_id=None, candidates=[])
    rows = (
        await db.execute(
            select(Company).where(
                Company.workspace_id == workspace_id,
                Company.normalized_name == key,
                Company.archived_at.is_(None),  # confirm the soft-delete column name in companies.models
            )
        )
    ).scalars().all()
    if not rows:
        return CompanyMatch(action="create", company_id=None, candidates=[])
    if len(rows) == 1:
        return CompanyMatch(action="update", company_id=rows[0].id, candidates=[])
    return CompanyMatch(
        action="ambiguous",
        company_id=None,
        candidates=[{"id": str(r.id), "name": r.name} for r in rows],
    )
```

> **Note for the implementer:** verify `Company.normalized_name` and the soft-delete column (`archived_at` vs `deleted_at`) by reading `apps/api/app/companies/models.py`. Adjust the filter to the real column. Triagram "similar name" candidates (the >1 fuzzy case from the spec) are out of scope for v1 — exact-normalized match only; note this in the conflict-card copy.

- [ ] **Step 5: Run tests to confirm pass**

Run: `cd apps/api && uv run pytest tests/base_update/test_services_match.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/base_update/services.py apps/api/tests/base_update/test_services_match.py
git commit -m "feat(base_update): company matching service + tests"
```

---

### Task 9: Auto-apply writer + conflict creation

**Files:**
- Modify: `apps/api/app/base_update/services.py` (add `apply_record`)
- Test: `apps/api/tests/base_update/test_services_apply.py`

`apply_record(db, job, record, group)` is the core writer: given a dedup group + its DB match, it auto-writes the safe parts and creates `IngestConflict` rows for the rest. It returns the record `action`.

- [ ] **Step 1: Write the failing test (new company → create lead in pool + needs_review + contacts + brief)**

```python
# apps/api/tests/base_update/test_services_apply.py
import pytest

from app.base_update import constants as c
from app.base_update.services import apply_record
from app.base_update.schemas import ExtractedCard


@pytest.mark.asyncio
async def test_new_company_creates_pool_lead_with_needs_review(session, seed_workspace):
    ws = seed_workspace
    card = ExtractedCard.model_validate({
        "company": {"name": "ООО НовыйКлиент", "city": "Казань", "priority": "B"},
        "contacts": [{"name": "Анна Смирнова", "title": "Закупки", "role_type": "operational_buyer"}],
        "ai_brief": "Региональная сеть, 8 точек.",
        "extraction_confidence": 0.9,
    })
    record = await _make_record(session, ws, card, ["new.md"])
    action = await apply_record(session, workspace_id=ws.id, record=record, card=card,
                                source_files=["new.md"], dedup_conflict=None)
    assert action == c.ACTION_CREATED
    # lead exists, in pool, needs_review, source=base_update, contact + brief attached
    lead = await _fetch_lead(session, record.match_lead_id)
    assert lead.assignment_status == "pool"
    assert lead.needs_review is True
    assert lead.source == "base_update"
```

(Helpers `_make_record`, `_fetch_lead` are small inline test utilities — write them in the test file: `_make_record` inserts an `IngestRecord` bound to a fresh `IngestJob`; `_fetch_lead` does a `session.get(Lead, id)`.)

- [ ] **Step 2: Write the failing test (existing company, empty field → autofill; filled+different → conflict)**

```python
@pytest.mark.asyncio
async def test_existing_company_autofills_empty_and_conflicts_on_diff(
    session, seed_workspace, make_company_with_lead
):
    ws = seed_workspace
    comp, lead = await make_company_with_lead(workspace_id=ws.id, name="ООО Ромашка", city=None, segment="QSR")
    card = ExtractedCard.model_validate({
        "company": {"name": "Ромашка", "city": "Москва", "segment": "HoReCa"},  # city empty→fill, segment differs→conflict
        "extraction_confidence": 0.9,
    })
    record = await _make_record(session, ws, card, ["r.md"])
    action = await apply_record(session, workspace_id=ws.id, record=record, card=card,
                                source_files=["r.md"], dedup_conflict=None)
    assert action == c.ACTION_CONFLICT
    await session.refresh(comp)
    assert comp.city == "Москва"           # autofilled
    conflicts = await _fetch_conflicts(session, record.id)
    assert any(cf.type == c.C_FIELD_MISMATCH and cf.field_name == "segment" for cf in conflicts)
```

- [ ] **Step 3: Run to confirm failure**

Run: `cd apps/api && uv run pytest tests/base_update/test_services_apply.py -v`
Expected: FAIL — `apply_record` missing.

- [ ] **Step 4: Implement `apply_record`**

Implement in `services.py`. Sketch (fill against real service signatures from the reference doc — `companies.services.update_company`, direct `Lead(...)` build per `_create_lead_from_email_payload`, `contacts.services.create_contact`):

```python
from app.base_update import constants as c
from app.base_update.matcher import classify_field, match_contact, is_low_confidence
from app.base_update.models import IngestConflict, IngestRecord
from app.companies.schemas import CompanyCreate, CompanyUpdate
from app.companies import services as companies_svc
from app.contacts import services as contacts_svc
from app.leads.models import Lead
from app.pipelines import repositories as pipelines_repo


async def apply_record(db, *, workspace_id, record: IngestRecord, card, source_files, dedup_conflict):
    # 0. #5 low confidence / #6 batch dup → conflict, skip auto-write
    conflicts: list[IngestConflict] = []
    if is_low_confidence(card.extraction_confidence, company_name=card.company.name):
        conflicts.append(_conflict(record, c.C_LOW_CONFIDENCE, c.TK_COMPANY, None,
                                   None, card.company.name))
    if dedup_conflict:
        conflicts.append(_conflict(record, c.C_BATCH_DUPLICATE, c.TK_COMPANY,
                                   dedup_conflict, None, None))

    match = await match_company(db, workspace_id=workspace_id, name=card.company.name)

    if match.action == "ambiguous":
        conflicts.append(_conflict(record, c.C_COMPANY_AMBIGUOUS, c.TK_COMPANY, None,
                                   None, card.company.name, candidates=match.candidates))
        for cf in conflicts:
            db.add(cf)
        record.action = c.ACTION_CONFLICT
        return c.ACTION_CONFLICT

    had_conflict = bool(conflicts)

    if match.action == "create":
        company = await companies_svc.create_company(
            db, workspace_id=workspace_id,
            data=CompanyCreate(name=card.company.name, city=card.company.city,
                               segment=card.company.segment, website=card.company.website,
                               inn=card.company.inn, phone=card.company.phone,
                               email=card.company.email),
            force=True,
        )
        pipeline_id, stage_id = await pipelines_repo.get_default_first_stage(db, workspace_id)
        lead = Lead(workspace_id=workspace_id, pipeline_id=pipeline_id, stage_id=stage_id,
                    company_id=company.id, company_name=company.name,
                    assignment_status="pool", tags_json=[], source="base_update",
                    needs_review=True, ai_data={"base_update_brief": card.ai_brief})
        db.add(lead); await db.flush()
        record.match_company_id = company.id
        record.match_lead_id = lead.id
        for ctc in card.contacts:
            await contacts_svc.create_contact(db, workspace_id, lead.id,
                {"name": ctc.name, "title": ctc.title, "role_type": ctc.role_type,
                 "email": ctc.email, "phone": ctc.phone, "telegram": ctc.telegram,
                 "linkedin": ctc.linkedin, "source": "base_update", "verified_status": "to_verify"})
        for cf in conflicts:
            db.add(cf)
        record.action = c.ACTION_CONFLICT if had_conflict else c.ACTION_CREATED
        return record.action

    # match.action == "update": autofill empty company fields, conflict on diffs
    company = await companies_svc.get_card(db, workspace_id=workspace_id, company_id=match.company_id)
    record.match_company_id = company.id
    updates = {}
    for fld in c.DIFFABLE_FIELDS:
        if not hasattr(company, fld):   # email/phone may live on company; skip if absent
            continue
        verdict = classify_field(base=getattr(company, fld), incoming=getattr(card.company, fld, None))
        if verdict == "autofill":
            updates[fld] = getattr(card.company, fld)
        elif verdict == "conflict":
            conflicts.append(_conflict(record, c.C_FIELD_MISMATCH, c.TK_COMPANY, fld,
                                       str(getattr(company, fld)), str(getattr(card.company, fld))))
    if updates:
        await companies_svc.update_company(db, workspace_id=workspace_id,
                                            company_id=company.id, data=CompanyUpdate(**updates))
    # lead target (#4): query leads for this company
    record.match_lead_id = await _resolve_or_conflict_lead_target(db, workspace_id, company.id, record, conflicts)
    # contacts (#3) + brief handled here (see steps below)
    for cf in conflicts:
        db.add(cf)
    record.action = c.ACTION_CONFLICT if conflicts else c.ACTION_UPDATED
    return record.action


def _conflict(record, type_, target_kind, field_name, base_value, incoming_value, candidates=None):
    return IngestConflict(
        ingest_job_id=record.ingest_job_id, ingest_record_id=record.id,
        type=type_, target_kind=target_kind, field_name=field_name,
        base_value=base_value, incoming_value=incoming_value,
        candidates_json=candidates, status=c.CONFLICT_OPEN,
    )
```

> Implement `_resolve_or_conflict_lead_target` (0 leads → create pool lead; 1 → use it; >1 → `C_LEAD_TARGET` conflict with candidates) and the contact-match loop (`match_contact` over the lead's existing contacts: no match → auto-add `to_verify`; name match + different details → `C_CONTACT_MISMATCH`) and brief (`autofill` if lead has no brief else `C_FIELD_MISMATCH` on `TK_BRIEF`) following the same `_conflict` pattern. Add one test per branch.

- [ ] **Step 5: Run tests to confirm pass**

Run: `cd apps/api && uv run pytest tests/base_update/test_services_apply.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/base_update/services.py apps/api/tests/base_update/test_services_apply.py
git commit -m "feat(base_update): auto-apply writer + conflict creation"
```

---

### Task 10: Resolution applier

**Files:**
- Modify: `apps/api/app/base_update/services.py` (add `resolve_conflict`, `apply_resolutions`)
- Test: `apps/api/tests/base_update/test_services_resolve.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/base_update/test_services_resolve.py
import pytest
from app.base_update import constants as c
from app.base_update.services import apply_resolutions


@pytest.mark.asyncio
async def test_overwrite_resolution_writes_incoming_value(
    session, seed_workspace, make_field_conflict
):
    ws = seed_workspace
    job, conflict, company = await make_field_conflict(
        workspace_id=ws.id, field="segment", base="QSR", incoming="HoReCa",
    )
    conflict.resolution = c.R_OVERWRITE
    conflict.status = c.CONFLICT_RESOLVED
    await session.commit()
    await apply_resolutions(session, job_id=job.id)
    await session.refresh(company)
    assert company.segment == "HoReCa"


@pytest.mark.asyncio
async def test_keep_resolution_leaves_base(session, seed_workspace, make_field_conflict):
    ws = seed_workspace
    job, conflict, company = await make_field_conflict(
        workspace_id=ws.id, field="segment", base="QSR", incoming="HoReCa",
    )
    conflict.resolution = c.R_KEEP
    conflict.status = c.CONFLICT_RESOLVED
    await session.commit()
    await apply_resolutions(session, job_id=job.id)
    await session.refresh(company)
    assert company.segment == "QSR"
```

- [ ] **Step 2: Run to confirm failure** — `apply_resolutions` missing.

- [ ] **Step 3: Implement `resolve_conflict` (persists a single decision — used by the PATCH endpoint) and `apply_resolutions` (iterates resolved conflicts, dispatches by `(type, target_kind, resolution)` to the right service write, flips job to `done` when no `open` conflicts remain).** Dispatch table:
  - `C_FIELD_MISMATCH` + `R_OVERWRITE` → `update_company`/lead/brief with `incoming_value`
  - `+ R_MANUAL` → write `resolved_value`
  - `+ R_KEEP`/`R_SKIP` → no write
  - `C_COMPANY_AMBIGUOUS` + `R_PICK` → attach record to `resolved_value` company id; `R_KEEP`(create new) → run the create path
  - `C_CONTACT_MISMATCH` + `R_OVERWRITE` (update contact) / `R_ADD_SEPARATE` (new contact) / `R_KEEP`/`R_SKIP`
  - `C_LEAD_TARGET` + `R_PICK` (use lead id) / `R_KEEP` (create new lead)
  - `C_LOW_CONFIDENCE` + `R_MANUAL` (apply corrected card) / `R_SKIP`
  - `C_BATCH_DUPLICATE` + `R_KEEP`(merge) / `R_ADD_SEPARATE`(create both)

  Write one test per dispatch branch you implement.

- [ ] **Step 4: Run tests to confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/base_update/services.py apps/api/tests/base_update/test_services_resolve.py
git commit -m "feat(base_update): resolution applier (apply_resolutions) + tests"
```

---

## Phase 4 — Orchestrator + Celery wrappers

### Task 11: Orchestrator cores

**Files:**
- Create: `apps/api/app/base_update/orchestrator.py`

- [ ] **Step 1: Write `run_extract_and_match(db, job_id)`** — best-effort per file (a failed extract → record with `C_LOW_CONFIDENCE`, others continue; budget exhausted → stop, job partial with reason in `error`). Sequence:
  1. Load job, set `status=EXTRACTING`, commit.
  2. For each stored `.md` text: `has_budget_remaining` check → `extract_card`. Collect `(card, [filename])`.
  3. `dedup_batch(...)` → groups. Set `status=MATCHING`.
  4. For each group: create `IngestRecord`, `apply_record(...)`, accumulate stats.
  5. Compute `stats_json` (companies created / leads created / contacts added / fields filled / conflicts total / open), `status=READY`, commit.
  Wrap each per-file and per-group body in try/except writing `record.error`; never let one failure abort the batch.

- [ ] **Step 2: Write `run_apply_resolutions(db, job_id)`** — set `status=RESOLVING`, call `apply_resolutions`, recompute open-conflict count, set `status=DONE` (or back to `READY` if some remain), commit.

- [ ] **Step 3: Verify import compiles**

Run: `cd apps/api && uv run python -m py_compile app/base_update/orchestrator.py`

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/base_update/orchestrator.py
git commit -m "feat(base_update): orchestrator cores (extract_and_match, apply_resolutions)"
```

> Where are the `.md` bytes stored between upload and the Celery run? Follow the spec's "временное хранилище": store each file's decoded text in `IngestRecord`-adjacent staging — simplest is to stash the list of `{filename, text}` in `IngestJob.stats_json["_staged_files"]` at upload time (texts are small `.md`), then the orchestrator reads them and clears the key. If files can be large, use `import_export/redis_bytes` with a TTL instead. Decide in Task 13; keep the orchestrator reading from one accessor `_load_staged_files(job)`.

---

### Task 12: Celery task wrappers

**Files:**
- Modify: `apps/api/app/scheduled/jobs.py`

- [ ] **Step 1: Add two task wrappers** (mirror `run_enrichment_task`):

```python
@celery_app.task(name="app.scheduled.jobs.base_update_extract")
def base_update_extract(job_id: str) -> dict:
    from uuid import UUID
    from app.base_update.orchestrator import run_extract_and_match
    async def _core():
        engine, factory = _build_task_engine_and_factory()
        try:
            async with factory() as db:
                await run_extract_and_match(db=db, job_id=UUID(job_id))
        finally:
            await engine.dispose()
        return {"job": "base_update_extract", "job_id": job_id}
    return asyncio.run(_core())


@celery_app.task(name="app.scheduled.jobs.base_update_apply")
def base_update_apply(job_id: str) -> dict:
    from uuid import UUID
    from app.base_update.orchestrator import run_apply_resolutions
    async def _core():
        engine, factory = _build_task_engine_and_factory()
        try:
            async with factory() as db:
                await run_apply_resolutions(db=db, job_id=UUID(job_id))
        finally:
            await engine.dispose()
        return {"job": "base_update_apply", "job_id": job_id}
    return asyncio.run(_core())
```

- [ ] **Step 2: Verify the worker registers the tasks**

Run: `cd apps/api && uv run python -c "from app.scheduled.celery_app import celery_app; print('app.scheduled.jobs.base_update_extract' in celery_app.tasks)"`
Expected: `True`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/scheduled/jobs.py
git commit -m "feat(base_update): celery task wrappers (extract, apply)"
```

---

## Phase 5 — REST API

### Task 13: REST DTOs + routers + upload

**Files:**
- Create: `apps/api/app/base_update/api_schemas.py`
- Create: `apps/api/app/base_update/routers.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/base_update/test_api_integration.py` (the upload + 202 + status path; full e2e is Task 16)

- [ ] **Step 1: Write `api_schemas.py`** — `IngestJobOut`, `IngestRecordOut`, `IngestConflictOut`, `ResolveConflictIn{resolution: str, resolved_value: str | None}`, all with `model_config = ConfigDict(from_attributes=True)`.

- [ ] **Step 2: Write `routers.py`**

```python
# apps/api/app/base_update/routers.py
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_head
from app.auth.models import User
from app.base_update import api_schemas as dto
from app.base_update import services as svc
from app.config import get_settings
from app.db import get_db

router = APIRouter(prefix="/api/base-update", tags=["base_update"])


@router.post("/jobs", response_model=dto.IngestJobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    files: Annotated[list[UploadFile], File(...)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_or_head)],
) -> dto.IngestJobOut:
    settings = get_settings()
    staged: list[dict] = []
    for f in files:
        if not (f.filename or "").lower().endswith(".md"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"только .md: {f.filename}")
        raw = await f.read()
        staged.append({"filename": f.filename, "text": raw.decode("utf-8", errors="replace")})
    job = await svc.create_job(db, workspace_id=user.workspace_id, user_id=user.id, staged=staged)
    await db.commit()
    from app.scheduled.celery_app import celery_app
    celery_app.send_task("app.scheduled.jobs.base_update_extract", args=[str(job.id)])
    return dto.IngestJobOut.model_validate(job)


@router.get("/jobs/{job_id}", response_model=dto.IngestJobOut)
async def get_job(job_id, db=Depends(get_db), user=Depends(require_admin_or_head)):
    return dto.IngestJobOut.model_validate(await svc.get_job(db, workspace_id=user.workspace_id, job_id=job_id))


@router.get("/jobs/{job_id}/conflicts", response_model=list[dto.IngestConflictOut])
async def list_conflicts(job_id, only_open: bool = True, db=Depends(get_db), user=Depends(require_admin_or_head)):
    return await svc.list_conflicts(db, workspace_id=user.workspace_id, job_id=job_id, only_open=only_open)


@router.patch("/conflicts/{conflict_id}", response_model=dto.IngestConflictOut)
async def resolve(conflict_id, body: dto.ResolveConflictIn, db=Depends(get_db), user=Depends(require_admin_or_head)):
    cf = await svc.resolve_conflict(db, workspace_id=user.workspace_id, conflict_id=conflict_id,
                                    resolution=body.resolution, resolved_value=body.resolved_value,
                                    resolved_by=user.id)
    await db.commit()
    return dto.IngestConflictOut.model_validate(cf)


@router.post("/jobs/{job_id}/apply", response_model=dto.IngestJobOut, status_code=status.HTTP_202_ACCEPTED)
async def apply(job_id, db=Depends(get_db), user=Depends(require_admin_or_head)):
    job = await svc.mark_resolving(db, workspace_id=user.workspace_id, job_id=job_id)
    await db.commit()
    from app.scheduled.celery_app import celery_app
    celery_app.send_task("app.scheduled.jobs.base_update_apply", args=[str(job.id)])
    return dto.IngestJobOut.model_validate(job)


@router.get("/jobs", response_model=list[dto.IngestJobOut])
async def list_jobs(limit: int = 20, offset: int = 0, db=Depends(get_db), user=Depends(require_admin_or_head)):
    return await svc.list_jobs(db, workspace_id=user.workspace_id, limit=limit, offset=offset)
```

> Implement the small service helpers used here: `create_job(staged=...)` (persists `IngestJob` with `file_count`, `source_filenames`, and stashes `staged` per the Task 11 staging decision), `get_job`, `list_conflicts`, `mark_resolving`, `list_jobs`. All filter on `workspace_id`; raise `HTTPException(404)` on miss.

- [ ] **Step 3: Register the router** in `apps/api/app/main.py`:
```python
from app.base_update.routers import router as base_update_router
app.include_router(base_update_router)
```

- [ ] **Step 4: Write the integration test** (upload 2 `.md`, assert 202 + job row with `file_count=2`, `status=pending`; mock `celery_app.send_task` so nothing dispatches). Use the project's async test client fixture.

- [ ] **Step 5: Run + commit**

Run: `cd apps/api && uv run pytest tests/base_update/test_api_integration.py -v` → pass.
```bash
git add apps/api/app/base_update/api_schemas.py apps/api/app/base_update/routers.py apps/api/app/main.py apps/api/tests/base_update/test_api_integration.py
git commit -m "feat(base_update): REST API (jobs/conflicts/apply) + upload"
```

---

## Phase 6 — Frontend (Settings section)

### Task 14: Types + hooks

**Files:**
- Modify: `apps/web/lib/types.ts` (add `IngestJobOut`, `IngestRecordOut`, `IngestConflictOut`)
- Create: `apps/web/lib/hooks/use-base-update.ts`

- [ ] **Step 1: Add the TS types** mirroring the DTOs (status string union, stats shape, conflict fields).

- [ ] **Step 2: Write the hooks** — copy the polling shape from `lib/hooks/use-import.ts`:
  - `useCreateIngestJob()` — raw `fetch` multipart (no Content-Type header), bearer token, returns `IngestJobOut`.
  - `useIngestJob(jobId)` — `useQuery` with `refetchInterval` = 2000ms while `status` ∈ {pending, extracting, matching, resolving}, else false.
  - `useConflicts(jobId)` — `api.get` list, enabled when status ∈ {ready, resolving}.
  - `useResolveConflict(jobId)` — `useMutation` PATCH, invalidates `["base-update-conflicts", jobId]`.
  - `useApplyResolutions(jobId)` — `useMutation` POST apply, `setQueryData(["base-update-job", jobId], data)`.

- [ ] **Step 3: Typecheck + commit**

Run: `cd apps/web && npm run typecheck` → clean.
```bash
git add apps/web/lib/types.ts apps/web/lib/hooks/use-base-update.ts
git commit -m "feat(base_update): web types + query hooks"
```

---

### Task 15: BaseUpdateSection + ConflictCard

**Files:**
- Create: `apps/web/components/settings/BaseUpdateSection.tsx`
- Create: `apps/web/components/settings/base-update/ConflictCard.tsx`
- Modify: `apps/web/app/(app)/settings/page.tsx`

- [ ] **Step 1: `BaseUpdateSection`** — three states keyed off the polled job:
  1. **idle:** drag-and-drop `.md` zone (`<input type="file" accept=".md" multiple>`), «Загрузить и разобрать» button → `useCreateIngestJob`.
  2. **running** (`extracting`/`matching`): progress copy + spinner (poll drives it).
  3. **ready/resolving:** stats summary (created/updated/contacts/fields + open conflicts) + a list of `<ConflictCard>` for each open conflict + a sticky «Применить решения» button (disabled while any conflict is `open`) → `useApplyResolutions`. On `done`: success summary + «Загрузить ещё».
  Use brand tokens (`bg-white border border-brand-border rounded-2xl`, `text-brand-*`, `bg-brand-accent text-white`), light theme, the app's existing settings-section spacing.

- [ ] **Step 2: `ConflictCard`** — renders one conflict with «В базе … / Из карточки …» and per-`type` action buttons (the 6 sets from the spec §Экран.3). Each button calls `useResolveConflict` with the right `{resolution, resolved_value}`. `R_MANUAL`/`R_PICK` reveal an input/select first. After resolve, the card collapses to a one-line resolved summary.

- [ ] **Step 3: Register the section** in `settings/page.tsx`: add `{ key: "base_update", label: "Обновление базы", icon: <UploadCloud/>, ready: true }` to `SECTIONS`, import `BaseUpdateSection`, render `{active === "base_update" && <BaseUpdateSection />}`. Keep the `useSearchParams` Suspense boundary intact.

- [ ] **Step 4: Mandatory frontend checks** (CLAUDE.md pre-PR — this adds non-literal nav/section state):

Run: `cd apps/web && npm run typecheck && npm run lint && npm run build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/settings/BaseUpdateSection.tsx apps/web/components/settings/base-update/ConflictCard.tsx "apps/web/app/(app)/settings/page.tsx"
git commit -m "feat(base_update): Settings section — upload, progress, conflict resolution"
```

---

## Phase 7 — End-to-end integration + docs

### Task 16: End-to-end integration test (mocked LLM)

**Files:**
- Create: `apps/api/tests/base_update/test_e2e.py`
- Add fixtures: `apps/api/tests/base_update/fixtures/*.md` (copy 3–4 real cards from `~/Desktop/DrinkX_Retail_LPR` and `DrinkX_AZS_LPR`, including a Газпромнефть/Лукойл pair that appears in both folders to exercise #6, and a Дикси card).

- [ ] **Step 1: Write the e2e test** — monkeypatch `extractor.complete_with_fallback` to return canned JSON per fixture; drive `run_extract_and_match` directly (no Celery): assert records created, a #6 conflict for the duplicated company, leads in pool with `needs_review`, and that Дикси is NOT attached to any X5/`purchase@x5.ru` entity (per memory `lead-data-diksi-x5`). Then resolve all conflicts and run `run_apply_resolutions`; assert job `status=done`, open conflicts = 0.

- [ ] **Step 2: Run the whole backend suite**

Run: `cd apps/api && uv run pytest tests/base_update/ -v`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/base_update/
git commit -m "test(base_update): end-to-end integration with mocked LLM + real .md fixtures"
```

---

### Task 17: Docs + brain update

**Files:**
- Modify: `docs/brain/00_CURRENT_STATE.md` (note the new domain)
- Create: `docs/features/base-update.md` (technical) — short: what it does, the job lifecycle, the 6 conflict types, where the section lives.

- [ ] **Step 1: Write the docs**, **Step 2: Commit**

```bash
git add docs/brain/00_CURRENT_STATE.md docs/features/base-update.md
git commit -m "docs(base_update): feature doc + current-state note"
```

---

## Self-Review (run before opening the PR)

- **Spec coverage:** входной `.md` ✓(T13), AI-извлечение ✓(T4–5), авто-запись безопасного ✓(T9), дедуп «только недостающее» ✓(T7,T9), новые лиды в пул+`needs_review` ✓(T9), доступ admin/head ✓(T13), перенос компании+ЛПР+бриф ✓(T9); все 6 конфликтов ✓(T9 create, T10 apply, T15 UI); API ✓(T13); async/Celery ✓(T11–12); error-handling best-effort ✓(T11); тесты unit+integration ✓(T4–10,16). **Gap to watch:** triagram fuzzy company match (>1 similar) is descoped to exact-normalized in v1 — confirm acceptable with product or add a follow-up task.
- **Type consistency:** `apply_record`, `match_company`/`CompanyMatch`, `classify_field`, `match_contact`, `dedup_batch`/`DedupGroup`, conflict constants — names used identically across tasks. The Celery task names (`app.scheduled.jobs.base_update_extract` / `_apply`) match between T12 dispatch and T11/T13 `send_task` calls.
- **Placeholder scan:** the two prose-described stretches (T9 contact/lead-target branches, T10 dispatch table, T15 UI per-type buttons) intentionally describe branch logic rather than dumping ~600 lines — each names exact functions/constants and demands a test per branch. Everything else has concrete code.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-22-base-update.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
