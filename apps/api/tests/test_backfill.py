"""Backfill of normalized dedup keys on legacy rows (DB-backed)."""
from __future__ import annotations

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.contacts.models import Contact
from app.leads.models import Lead
from app.common.backfill import backfill_normalized_keys

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


async def _legacy_lead(db, workspace_id, **kw):
    """A lead that looks pre-normalization: source fields set, derived keys NULL."""
    lead = Lead(workspace_id=workspace_id, company_name="Acme", assignment_status="pool", tags_json=[], **kw)
    db.add(lead)
    await db.flush()
    # The @validates hooks fill the keys on construction — null them to mimic a
    # row created before those hooks existed.
    lead.phone_e164 = None
    lead.email_normalized = None
    lead.email_domain_criterion = None
    await db.flush()
    return lead


@skip_no_pg
async def test_backfill_rederives_lead_keys(db, workspace):
    lead = await _legacy_lead(db, workspace.id, email="ivan@acme.ru", phone="89161234567")
    await db.commit()

    touched = await backfill_normalized_keys(db, batch_size=10)

    assert touched >= 1
    assert lead.email_normalized == "ivan@acme.ru"
    assert lead.email_domain_criterion == "acme.ru"
    assert lead.phone_e164 == "+79161234567"


@skip_no_pg
async def test_backfill_rederives_contact_keys(db, workspace):
    lead = Lead(workspace_id=workspace.id, company_name="Acme", assignment_status="pool", tags_json=[])
    db.add(lead)
    await db.flush()
    contact = Contact(lead_id=lead.id, workspace_id=workspace.id, name="Ivan",
                      email="ivan@acme.ru", phone="89161234567")
    db.add(contact)
    await db.flush()
    contact.email_normalized = None
    contact.phone_e164 = None
    await db.commit()

    await backfill_normalized_keys(db, batch_size=10)

    assert contact.email_normalized == "ivan@acme.ru"
    assert contact.phone_e164 == "+79161234567"


@skip_no_pg
async def test_backfill_is_idempotent(db, workspace):
    lead = await _legacy_lead(db, workspace.id, email="ivan@acme.ru", phone="89161234567")
    await db.commit()

    first = await backfill_normalized_keys(db, batch_size=10)
    # Second pass finds nothing left to fill → 0 rows touched.
    second = await backfill_normalized_keys(db, batch_size=10)

    assert first >= 1
    assert second == 0
    assert lead.phone_e164 == "+79161234567"


@skip_no_pg
async def test_backfill_skips_already_filled(db, workspace):
    # A normal lead (keys already derived by @validates) is not re-selected.
    lead = Lead(workspace_id=workspace.id, company_name="Acme", assignment_status="pool",
                tags_json=[], email="a@acme.ru", phone="89161234567")
    db.add(lead)
    await db.commit()

    touched = await backfill_normalized_keys(db, batch_size=10)
    assert touched == 0
