"""Sprint 3.5 G1 — segment vocabulary + city normalization.

Mock-only: tests the pure helpers + Pydantic validation. The /leads/cities
endpoint smoke-test lives in a route-level integration test (out of scope
for this module — the repo prefers thin route layers + verifying logic in
the supporting helpers).
"""
from __future__ import annotations

import pytest

from app.leads.constants import (
    SEGMENT_CHOICES,
    SEGMENT_KEYS,
    SEGMENT_LABELS,
    normalize_city,
)
from app.leads.schemas import LeadCreate, LeadUpdate


def test_segment_choices_has_eight_unique_keys() -> None:
    assert len(SEGMENT_CHOICES) == 8
    keys = [k for k, _ in SEGMENT_CHOICES]
    assert len(set(keys)) == 8
    assert SEGMENT_KEYS == keys


def test_segment_labels_match_choices() -> None:
    for key, label in SEGMENT_CHOICES:
        assert SEGMENT_LABELS[key] == label


def test_canonical_keys_present() -> None:
    expected = {
        "food_retail",
        "non_food_retail",
        "coffee_shops",
        "qsr_fast_food",
        "gas_stations",
        "office",
        "hotel",
        "distributor",
    }
    assert set(SEGMENT_KEYS) == expected


# ---------------------------------------------------------------------------
# City normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Москва", "Москва"),
        ("москва", "Москва"),
        ("  москва  ", "Москва"),
        ("г. Москва", "Москва"),
        ("г.Москва", "Москва"),
        ("г Москва", "Москва"),
        ("Г. Санкт-Петербург", "Санкт-Петербург"),
        ("", None),
        ("   ", None),
        ("г.  ", None),
        (None, None),
        ("новосибирск", "Новосибирск"),
    ],
)
def test_normalize_city(raw: str | None, expected: str | None) -> None:
    assert normalize_city(raw) == expected


# ---------------------------------------------------------------------------
# Pydantic validators
# ---------------------------------------------------------------------------


def test_lead_create_accepts_canonical_segment() -> None:
    lead = LeadCreate(company_name="Acme", segment="food_retail")
    assert lead.segment == "food_retail"


def test_lead_create_rejects_unknown_segment() -> None:
    with pytest.raises(ValueError, match="Invalid segment"):
        LeadCreate(company_name="Acme", segment="not_a_real_segment")


def test_lead_create_treats_empty_segment_as_none() -> None:
    lead = LeadCreate(company_name="Acme", segment="")
    assert lead.segment is None


def test_lead_create_normalizes_city() -> None:
    lead = LeadCreate(company_name="Acme", city="г. Москва")
    assert lead.city == "Москва"


def test_lead_update_rejects_unknown_segment() -> None:
    with pytest.raises(ValueError, match="Invalid segment"):
        LeadUpdate(segment="not_a_real_segment")


def test_lead_update_accepts_explicit_null_segment() -> None:
    payload = LeadUpdate(segment=None)
    assert payload.segment is None


def test_lead_update_normalizes_city() -> None:
    payload = LeadUpdate(city="  г.санкт-петербург  ")
    assert payload.city == "Санкт-петербург"
