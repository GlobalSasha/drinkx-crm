"""E.164 phone normalization (app.common.phone) + model auto-fill.

Pure unit tests — no DB. The @validates hook fires on attribute set during
ORM __init__, so `phone_e164` is populated without a session.
"""
from __future__ import annotations

import uuid

import pytest

from app.common.phone import to_e164
from app.leads.models import Lead
from app.contacts.models import Contact

# Trigger ORM mapper configuration — Lead has string-referenced relationships
# that must be importable before instances are built.
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+79161234567", "+79161234567"),
        ("89161234567", "+79161234567"),       # RU 8-prefix
        ("8 (916) 123-45-67", "+79161234567"),  # messy formatting
        ("+7 916 123 45 67", "+79161234567"),
        ("123", None),                          # too short
        ("not a phone", None),
        ("   ", None),
        ("", None),
        (None, None),
    ],
)
def test_to_e164(raw, expected):
    assert to_e164(raw) == expected


def test_lead_phone_sets_e164():
    lead = Lead(company_name="Acme", workspace_id=uuid.uuid4(), phone="8 (916) 123-45-67")
    assert lead.phone == "8 (916) 123-45-67"  # original kept verbatim
    assert lead.phone_e164 == "+79161234567"  # derived E.164


def test_lead_invalid_phone_yields_none():
    lead = Lead(company_name="Acme", workspace_id=uuid.uuid4(), phone="abc")
    assert lead.phone_e164 is None


def test_lead_phone_update_refreshes_e164():
    lead = Lead(company_name="Acme", workspace_id=uuid.uuid4(), phone="89161234567")
    assert lead.phone_e164 == "+79161234567"
    lead.phone = None
    assert lead.phone_e164 is None


def test_contact_phone_sets_e164():
    c = Contact(
        name="Ivan",
        workspace_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        phone="89161234567",
    )
    assert c.phone_e164 == "+79161234567"
