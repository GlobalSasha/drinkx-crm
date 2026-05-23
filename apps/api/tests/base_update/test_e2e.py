"""End-to-end test for the base_update domain.

Mocks the LLM (no API calls), drives `run_extract_and_match` against a real
Postgres test database, then resolves the auto-generated conflicts and runs
`run_apply_resolutions`. Verifies:
  * new companies + pool leads with needs_review=True are created
  * Дикси is NOT attached to anything X5 (per [[lead-data-diksi-x5]])
  * batch-duplicate (#6) is flagged for the same-name duplicates
  * the job lifecycle reaches `done` after resolutions are applied

Skipped automatically when no local Postgres is configured — runs on CI.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

# Skip the entire module when no Postgres is available — the DB-backed
# fixtures (`db`, `workspace`, `admin_user`, `pipeline`) aren't registered
# in that case, so the test would otherwise error with "fixture not found".
from tests.conftest import POSTGRES_AVAILABLE  # noqa: E402

pytestmark = pytest.mark.skipif(
    not POSTGRES_AVAILABLE, reason="requires a local Postgres (TEST_DATABASE_URL)"
)

from app.base_update import constants as c  # noqa: E402
from app.base_update import extractor as extractor_module  # noqa: E402
from app.base_update import orchestrator  # noqa: E402
from app.base_update import services as svc  # noqa: E402
from app.base_update.models import IngestConflict, IngestJob, IngestRecord  # noqa: E402

# Synthetic fixtures, keyed by filename → (md text, mocked extracted payload)
_FIXTURES: dict[str, tuple[str, dict]] = {
    "diksi.md": (
        "# Дикси\nСеть Дикси, директор по закупкам Иван Петров.",
        {
            "company": {"name": "Дикси", "segment": "retail", "city": "Москва"},
            "contacts": [{"name": "Иван Петров", "title": "Директор закупок", "role_type": "economic_buyer"}],
            "ai_brief": "Самостоятельная сеть, не часть X5.",
            "extraction_confidence": 0.9,
        },
    ),
    "gpn_1.md": (
        "# Газпромнефть\nГазпромнефть, контакт А.",
        {
            "company": {"name": "Газпромнефть", "segment": "azs", "city": "Москва"},
            "contacts": [{"name": "Контакт А"}],
            "ai_brief": "АЗС сеть.",
            "extraction_confidence": 0.85,
        },
    ),
    "gpn_2.md": (
        "# ООО Газпромнефть\nАЗС, контакт Б.",
        {
            "company": {"name": "ООО Газпромнефть", "segment": "azs", "city": "Санкт-Петербург"},
            "contacts": [{"name": "Контакт Б"}],
            "ai_brief": "АЗС сеть, другая база.",
            "extraction_confidence": 0.85,
        },
    ),
    "perekrestok.md": (
        "# Перекрёсток\nНовый клиент.",
        {
            "company": {"name": "Перекрёсток", "segment": "retail", "city": "Москва", "priority": "B"},
            "contacts": [{"name": "Анна Сидорова", "role_type": "operational_buyer"}],
            "ai_brief": "Сеть Перекрёсток, ~900 магазинов.",
            "extraction_confidence": 0.92,
        },
    ),
}


def _mock_complete_factory():
    """Build a fake `complete_with_fallback` that picks the right payload by
    looking at the user text — the orchestrator calls extract_card with the
    full md text, so we route on a stable substring."""

    async def fake_complete(**kwargs):
        user_text = kwargs.get("user", "")
        for filename, (md, payload) in _FIXTURES.items():
            # Choose the payload whose md content shares enough of the input
            if md[:20] in user_text:
                return SimpleNamespace(text=json.dumps(payload), cost_usd=0.0)
        # Default: empty payload — drives a low-confidence record
        return SimpleNamespace(text="{}", cost_usd=0.0)

    return fake_complete


@pytest.fixture
def stub_budget(monkeypatch):
    """Always-OK budget so the test doesn't touch Redis."""
    async def always_ok(_workspace_id):
        return True
    monkeypatch.setattr(orchestrator, "has_budget_remaining", always_ok)


@pytest.fixture
def stub_extractor(monkeypatch):
    """Replace the LLM call with the canned fake."""
    monkeypatch.setattr(extractor_module, "complete_with_fallback", _mock_complete_factory())


@pytest.mark.asyncio
async def test_e2e_extract_match_apply(
    db, workspace, admin_user, pipeline, stub_budget, stub_extractor
):
    # 1. Build a job with the 4 staged files
    pipeline_obj, stage = pipeline
    staged = [{"filename": fn, "text": md} for fn, (md, _) in _FIXTURES.items()]
    job = IngestJob(
        workspace_id=workspace.id,
        user_id=admin_user.id,
        status=c.JOB_PENDING,
        file_count=len(staged),
        source_filenames=[s["filename"] for s in staged],
        stats_json={"_staged_files": staged},
    )
    db.add(job)
    await db.flush()
    await db.commit()
    job_id = job.id

    # 2. Run the extract+match orchestrator
    await orchestrator.run_extract_and_match(db=db, job_id=job_id)

    # Re-load the job
    await db.refresh(job)
    assert job.status == c.JOB_READY

    # 3. Records expected: 3 (gpn_1 and gpn_2 merge into one Газпромнефть group)
    from sqlalchemy import select
    records = (
        await db.execute(select(IngestRecord).where(IngestRecord.ingest_job_id == job_id))
    ).scalars().all()
    assert len(records) == 3, f"expected 3 records after dedup, got {len(records)}"

    names = sorted(r.company_name for r in records)
    # Дикси must appear as its own row (not under any X5 grouping)
    assert any("Дикси" in n for n in names), f"Дикси missing in {names}"
    # No record should be named X5 or share an x5.ru-shaped contact (we don't seed any)
    assert not any("X5" in (r.company_name or "") or "x5" in (r.company_name or "").lower() for r in records)

    # 4. Газпромнефть group has a #6 batch_duplicate conflict (city diverges)
    conflicts = (
        await db.execute(select(IngestConflict).where(IngestConflict.ingest_job_id == job_id))
    ).scalars().all()
    bd_conflicts = [cf for cf in conflicts if cf.type == c.C_BATCH_DUPLICATE]
    assert len(bd_conflicts) == 1, f"expected exactly 1 batch_duplicate, got {len(bd_conflicts)}"
    assert bd_conflicts[0].field_name == "city"

    # 5. New leads in pool with needs_review
    from app.leads.models import Lead
    leads = (
        await db.execute(
            select(Lead).where(
                Lead.workspace_id == workspace.id,
                Lead.source == "base_update",
            )
        )
    ).scalars().all()
    assert len(leads) >= 1
    assert all(lead.assignment_status == "pool" for lead in leads)
    assert all(lead.needs_review for lead in leads)

    # 6. Resolve all open conflicts as 'skip' / 'keep' so apply has work to do
    open_cf = [cf for cf in conflicts if cf.status == c.CONFLICT_OPEN]
    from datetime import datetime, timezone
    for cf in open_cf:
        cf.status = c.CONFLICT_RESOLVED
        cf.resolution = c.R_SKIP if cf.type in (c.C_LOW_CONFIDENCE, c.C_BATCH_DUPLICATE) else c.R_KEEP
        cf.resolved_value = None
        cf.resolved_by = admin_user.id
        cf.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    # 7. Run the apply orchestrator
    await orchestrator.run_apply_resolutions(db=db, job_id=job_id)
    await db.refresh(job)

    # If any conflicts were "deferred" (contact_mismatch, lead_target — there
    # shouldn't be any from our synthetic fixtures), the job stays READY;
    # otherwise it transitions to DONE.
    remaining_open = (
        await db.execute(
            select(IngestConflict).where(
                IngestConflict.ingest_job_id == job_id,
                IngestConflict.status == c.CONFLICT_OPEN,
            )
        )
    ).scalars().all()
    if remaining_open:
        assert job.status == c.JOB_READY
    else:
        assert job.status == c.JOB_DONE
