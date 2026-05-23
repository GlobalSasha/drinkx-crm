"""Smoke tests for early-return branches in apply_record that don't touch
the DB. The full create/update paths are exercised by the e2e integration
test (Task 16) on CI with a real Postgres."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.base_update import constants as c
from app.base_update import services as svc
from app.base_update.models import IngestConflict
from app.base_update.schemas import ExtractedCard


def _fake_record():
    """Stand-in for an IngestRecord — apply_record only reads/sets a few attrs."""
    rec = SimpleNamespace(
        id="r1",
        ingest_job_id="j1",
        action=None,
        match_company_id=None,
        match_lead_id=None,
        source_files=None,
        confidence=None,
        error=None,
    )
    return rec


def _fake_db():
    """db.add stores conflicts; db.execute / flush aren't called on early-return paths."""
    added: list[IngestConflict] = []
    db = MagicMock()
    db.add = lambda obj: added.append(obj)
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db, added


@pytest.mark.asyncio
async def test_low_confidence_empty_name_short_circuits(monkeypatch):
    db, added = _fake_db()
    rec = _fake_record()
    card = ExtractedCard.model_validate({"extraction_confidence": 0.2})  # no name → low confidence by name + by score
    action = await svc.apply_record(
        db, workspace_id="ws1", record=rec, card=card, source_files=["x.md"], dedup_conflict_field=None
    )
    assert action == c.ACTION_CONFLICT
    assert rec.action == c.ACTION_CONFLICT
    assert any(cf.type == c.C_LOW_CONFIDENCE for cf in added)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_batch_duplicate_records_conflict(monkeypatch):
    """When the orchestrator passes a dedup_conflict_field, a #6 conflict is queued.
    We still proceed to match — so mock match_company to return 'create' and stub
    the create path enough to short-circuit before any DB writes."""
    db, added = _fake_db()
    rec = _fake_record()

    async def fake_match(db_, *, workspace_id, name):
        return svc.CompanyMatch(action="create")

    monkeypatch.setattr(svc, "match_company", fake_match)

    async def fake_create_company(db_, *, workspace_id, data, force):
        raise RuntimeError("stop here — we only care that the conflict was queued")

    monkeypatch.setattr(svc.companies_svc, "create_company", fake_create_company)

    card = ExtractedCard.model_validate({"company": {"name": "Лукойл"}, "extraction_confidence": 0.9})
    with pytest.raises(RuntimeError):
        await svc.apply_record(
            db, workspace_id="ws1", record=rec, card=card,
            source_files=["a.md", "b.md"], dedup_conflict_field="city",
        )
    assert any(cf.type == c.C_BATCH_DUPLICATE and cf.field_name == "city" for cf in added)


@pytest.mark.asyncio
async def test_ambiguous_match_records_company_ambiguous_conflict(monkeypatch):
    db, added = _fake_db()
    rec = _fake_record()

    async def fake_match(db_, *, workspace_id, name):
        return svc.CompanyMatch(action="ambiguous", candidates=[{"id": "c1", "name": "A"}, {"id": "c2", "name": "B"}])

    monkeypatch.setattr(svc, "match_company", fake_match)

    card = ExtractedCard.model_validate({"company": {"name": "Перекрёсток"}, "extraction_confidence": 0.9})
    action = await svc.apply_record(
        db, workspace_id="ws1", record=rec, card=card, source_files=["x.md"], dedup_conflict_field=None
    )
    assert action == c.ACTION_CONFLICT
    amb = [cf for cf in added if cf.type == c.C_COMPANY_AMBIGUOUS]
    assert len(amb) == 1
    assert amb[0].candidates_json == [{"id": "c1", "name": "A"}, {"id": "c2", "name": "B"}]


@pytest.mark.asyncio
async def test_pure_diff_company_fields_autofill_and_conflict():
    """Direct test of the pure _diff_company_fields helper."""
    card = ExtractedCard.model_validate({
        "company": {"name": "X", "segment": "HoReCa", "city": "Москва", "website": "https://x.ru"},
    })
    base = SimpleNamespace(primary_segment="QSR", website=None, inn=None, city="Москва", phone=None, email=None)
    updates, conflicts = svc._diff_company_fields(card, base)
    assert updates == {"website": "https://x.ru"}                  # base empty → autofill
    # The schema validator canonicalises "HoReCa" → "HORECA" (the canonical
    # Russian-label form Lead.segment uses verbatim). Conflict reports the
    # canonical incoming value.
    assert ("primary_segment", "QSR", "HORECA") in conflicts
    # city matches (case-insensitive normalized), nothing happens
    assert all(f != "city" for f, _, _ in conflicts) and "city" not in updates


# --- _decide_apply pure dispatch tests ---
from app.base_update import constants as c


def _cf(type_, *, target_kind=c.TK_COMPANY, field_name=None, incoming=None, resolved=None, resolution=None):
    """Tiny IngestConflict stand-in for the pure helper."""
    return SimpleNamespace(
        type=type_, target_kind=target_kind, field_name=field_name,
        incoming_value=incoming, resolved_value=resolved, resolution=resolution,
    )


def test_decide_apply_field_overwrite():
    op, args = svc._decide_apply(_cf(c.C_FIELD_MISMATCH, field_name="city", incoming="Москва", resolution=c.R_OVERWRITE))
    assert op == "update_company_field"
    assert args == {"field": "city", "value": "Москва"}


def test_decide_apply_field_manual_uses_resolved_value():
    op, args = svc._decide_apply(_cf(c.C_FIELD_MISMATCH, field_name="city", incoming="Москва", resolved="Санкт-Петербург", resolution=c.R_MANUAL))
    assert op == "update_company_field"
    assert args == {"field": "city", "value": "Санкт-Петербург"}


def test_decide_apply_field_keep_and_skip_are_noop():
    for r in (c.R_KEEP, c.R_SKIP):
        op, _ = svc._decide_apply(_cf(c.C_FIELD_MISMATCH, field_name="city", resolution=r))
        assert op == "noop"


def test_decide_apply_company_pick():
    op, args = svc._decide_apply(_cf(c.C_COMPANY_AMBIGUOUS, resolved="11111111-1111-1111-1111-111111111111", resolution=c.R_PICK))
    assert op == "set_match_company"
    assert args == {"company_id": "11111111-1111-1111-1111-111111111111"}


def test_decide_apply_low_confidence_manual_sets_error():
    op, args = svc._decide_apply(_cf(c.C_LOW_CONFIDENCE, resolved="скорректировано вручную", resolution=c.R_MANUAL))
    assert op == "set_record_error"
    assert "manual" in args["message"]


def test_decide_apply_low_confidence_skip_is_noop():
    op, _ = svc._decide_apply(_cf(c.C_LOW_CONFIDENCE, resolution=c.R_SKIP))
    assert op == "noop"


def test_decide_apply_batch_duplicate_keep_is_noop():
    op, _ = svc._decide_apply(_cf(c.C_BATCH_DUPLICATE, resolution=c.R_KEEP))
    assert op == "noop"


def test_decide_apply_contact_overwrite():
    cf = _cf(c.C_CONTACT_MISMATCH, target_kind=c.TK_CONTACT, field_name="phone",
             incoming="+7 999", resolved="contact-uuid-here", resolution=c.R_OVERWRITE)
    op, args = svc._decide_apply(cf)
    assert op == "update_contact_field"
    assert args == {"contact_id": "contact-uuid-here", "field": "phone", "value": "+7 999"}


def test_decide_apply_contact_keep_and_skip_are_noop():
    for r in (c.R_KEEP, c.R_SKIP):
        op, _ = svc._decide_apply(_cf(c.C_CONTACT_MISMATCH, target_kind=c.TK_CONTACT, resolution=r))
        assert op == "noop"


def test_decide_apply_contact_add_separate_returns_add_contact():
    payload = {"name": "Иван Петров", "phone": "+7 999"}
    cf = _cf(c.C_CONTACT_MISMATCH, target_kind=c.TK_CONTACT, resolution=c.R_ADD_SEPARATE)
    cf.candidates_json = [payload]
    op, args = svc._decide_apply(cf)
    assert op == "add_contact"
    assert args == {"contact_data": payload}


def test_decide_apply_contact_add_separate_empty_candidates():
    """Defensive: no candidates_json → empty contact_data, but still add_contact op."""
    cf = _cf(c.C_CONTACT_MISMATCH, target_kind=c.TK_CONTACT, resolution=c.R_ADD_SEPARATE)
    cf.candidates_json = None
    op, args = svc._decide_apply(cf)
    assert op == "add_contact"
    assert args == {"contact_data": {}}


def test_decide_apply_lead_target_pick():
    op, args = svc._decide_apply(_cf(c.C_LEAD_TARGET, target_kind=c.TK_LEAD,
                                     resolved="11111111-1111-1111-1111-111111111111",
                                     resolution=c.R_PICK))
    assert op == "set_match_lead"
    assert args == {"lead_id": "11111111-1111-1111-1111-111111111111"}


def test_decide_apply_lead_target_keep_creates_new():
    op, _ = svc._decide_apply(_cf(c.C_LEAD_TARGET, target_kind=c.TK_LEAD, resolution=c.R_KEEP))
    assert op == "create_new_lead"


def test_decide_apply_lead_target_skip_is_noop():
    op, _ = svc._decide_apply(_cf(c.C_LEAD_TARGET, target_kind=c.TK_LEAD, resolution=c.R_SKIP))
    assert op == "noop"


# --- FIX-1: eager-load smoke ---

def test_apply_resolutions_eager_loads_record():
    """Smoke: the select used in apply_resolutions includes selectinload(IngestConflict.record)."""
    import inspect
    src = inspect.getsource(svc.apply_resolutions)
    assert "selectinload" in src, "apply_resolutions must eager-load cf.record (avoids MissingGreenlet)"


# --- FIX-3: R_MANUAL with empty/None resolved_value is deferred ---

def test_decide_apply_field_manual_with_none_value_is_deferred():
    op, _ = svc._decide_apply(_cf(c.C_FIELD_MISMATCH, field_name="city", resolution=c.R_MANUAL, resolved=None))
    assert op == "deferred"


def test_decide_apply_field_manual_with_empty_string_is_deferred():
    op, _ = svc._decide_apply(_cf(c.C_FIELD_MISMATCH, field_name="city", resolution=c.R_MANUAL, resolved=""))
    assert op == "deferred"


def test_decide_apply_field_manual_with_whitespace_is_deferred():
    op, _ = svc._decide_apply(_cf(c.C_FIELD_MISMATCH, field_name="city", resolution=c.R_MANUAL, resolved="   "))
    assert op == "deferred"
