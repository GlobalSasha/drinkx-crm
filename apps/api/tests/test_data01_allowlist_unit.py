"""DATA-01: один набор допустимых `assignment_status` — и для выборки, и для
записи.

HTTP-поведение (4xx на трёх путях) проверяет отдельный тест QA; здесь —
сам набор значений и две точки, которые обязаны брать его из одного места.
Без этого allowlist легко разъезжается: колонка `String(20)` принимает что
угодно, а по всему приложению статус используется как инвариант
пул/закреплён.
"""
from __future__ import annotations

import pytest

from app.import_export.access import ExportFilterInvalid
from app.leads.models import ASSIGNMENT_STATUSES
from app.leads.schemas import LeadUpdate
from app.leads.selection import LeadSelection


def test_allowlist_matches_values_the_code_actually_writes():
    """`pool`/`assigned` пишет бэкенд, `deleted` — интерфейс при отклонении
    авто-созданной карточки. `transferred` из декоративного enum
    `AssignmentStatus` не пишет никто, поэтому в наборе его нет."""
    assert ASSIGNMENT_STATUSES == ("pool", "assigned", "deleted")


@pytest.mark.parametrize("value", ASSIGNMENT_STATUSES)
def test_selection_accepts_known_values(value):
    LeadSelection(assignment_status=value).validate_assignment_status()


def test_selection_without_status_is_not_rejected():
    LeadSelection().validate_assignment_status()


def test_selection_rejects_unknown_value():
    with pytest.raises(ExportFilterInvalid):
        LeadSelection(assignment_status="zzz").validate_assignment_status()


@pytest.mark.parametrize("value", ASSIGNMENT_STATUSES)
def test_lead_update_accepts_known_values(value):
    assert LeadUpdate(assignment_status=value).assignment_status == value


def test_lead_update_rejects_unknown_value():
    with pytest.raises(ValueError):
        LeadUpdate(assignment_status="zzz")


def test_lead_update_without_status_is_unchanged():
    payload = LeadUpdate(company_name="Ко")
    assert payload.model_dump(exclude_unset=True) == {"company_name": "Ко"}
