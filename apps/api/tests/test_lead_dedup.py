"""Email normalization + lead duplicate detection (Odoo dedup pattern).

Pure unit tests — no DB. The @validates hooks fire on attribute set during
ORM __init__; find_duplicates is exercised against a mocked AsyncSession.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.common.email import email_domain_criterion, normalize_email
from app.leads.dedup import DUP_LIMIT, find_duplicates
from app.leads.models import Lead
from app.contacts.models import Contact

# Trigger ORM mapper configuration (string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401


# ── normalize_email ───────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Ivan@Acme.RU", "ivan@acme.ru"),
        ("  user@host.com  ", "user@host.com"),
        ("not-an-email", None),
        ("nope@nodot", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


# ── email_domain_criterion (free-mail excluded) ───────────────────
@pytest.mark.parametrize(
    "email,expected",
    [
        ("ivan@acme.ru", "acme.ru"),      # corporate → domain kept
        ("petr@acme.ru", "acme.ru"),      # same company → same key
        ("someone@gmail.com", None),       # free-mail → no key
        ("someone@yandex.ru", None),
        ("someone@mail.ru", None),
        (None, None),
    ],
)
def test_email_domain_criterion(email, expected):
    assert email_domain_criterion(email) == expected


# ── model auto-fill ───────────────────────────────────────────────
def test_lead_email_sets_keys():
    lead = Lead(company_name="Acme", workspace_id=uuid.uuid4(), email="Ivan@Acme.ru")
    assert lead.email == "Ivan@Acme.ru"          # original kept
    assert lead.email_normalized == "ivan@acme.ru"
    assert lead.email_domain_criterion == "acme.ru"


def test_lead_freemail_has_no_domain_key():
    lead = Lead(company_name="Acme", workspace_id=uuid.uuid4(), email="vip@gmail.com")
    assert lead.email_normalized == "vip@gmail.com"
    assert lead.email_domain_criterion is None    # gmail is not a dedup signal


def test_contact_email_normalized():
    c = Contact(name="Ivan", workspace_id=uuid.uuid4(), lead_id=uuid.uuid4(), email="Ivan@Acme.ru")
    assert c.email_normalized == "ivan@acme.ru"


# ── find_duplicates ───────────────────────────────────────────────
def _db_returning(rows):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


async def test_find_duplicates_no_keys_skips_query():
    # No email / phone / company → nothing to match on; no DB call.
    lead = Lead(company_name="Acme", workspace_id=uuid.uuid4())
    db = _db_returning([])
    assert await find_duplicates(db, lead) == []
    db.execute.assert_not_called()


async def test_find_duplicates_returns_matches():
    ws = uuid.uuid4()
    lead = Lead(company_name="Acme", workspace_id=ws, email="ivan@acme.ru")
    dup = Lead(company_name="Acme LLC", workspace_id=ws, email="petr@acme.ru")
    db = _db_returning([dup])
    res = await find_duplicates(db, lead)
    assert res == [dup]
    db.execute.assert_awaited_once()


async def test_find_duplicates_suppresses_dupe_bomb():
    ws = uuid.uuid4()
    lead = Lead(company_name="Acme", workspace_id=ws, phone="89161234567")
    crowd = [Lead(company_name=f"x{i}", workspace_id=ws) for i in range(DUP_LIMIT)]
    db = _db_returning(crowd)
    assert await find_duplicates(db, lead) == []
