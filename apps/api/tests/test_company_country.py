"""Страна компании — отдельное поле рядом с городом и адресом.

Закреплено: страна сохраняется при создании и правке, не затирает город и
адрес, а слишком длинное значение отклоняется схемой.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.companies.schemas import CompanyCreate, CompanyOut, CompanyUpdate
from app.companies.services import create_company, update_company

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


@skip_no_pg
async def test_country_is_saved_on_create_and_update(db, workspace):
    company = await create_company(
        db,
        workspace_id=workspace.id,
        data=CompanyCreate(name="Сыр и кофе", city="Москва", country="Россия"),
        force=True,
    )
    assert company.country == "Россия"

    updated = await update_company(
        db,
        workspace_id=workspace.id,
        company_id=company.id,
        data=CompanyUpdate(country="Беларусь", address="пр. Независимости, 1"),
    )
    assert updated.country == "Беларусь"
    assert updated.city == "Москва"
    assert updated.address == "пр. Независимости, 1"
    assert CompanyOut.model_validate(updated).country == "Беларусь"


def test_too_long_country_is_rejected():
    with pytest.raises(ValidationError):
        CompanyUpdate(country="Р" * 81)
