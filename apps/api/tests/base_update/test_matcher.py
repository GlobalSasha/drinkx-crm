from app.base_update.matcher import (
    classify_field,
    is_low_confidence,
    match_contact,
    normalized_company_key,
)


def test_classify_field_empty_base_autofills():
    assert classify_field(base=None, incoming="Москва") == "autofill"
    assert classify_field(base="", incoming="Москва") == "autofill"
    assert classify_field(base="   ", incoming="Москва") == "autofill"


def test_classify_field_equal_is_noop():
    assert classify_field(base="Москва", incoming="москва ") == "noop"
    assert classify_field(base="HoReCa", incoming="HoReCa") == "noop"


def test_classify_field_diverging_is_conflict():
    assert classify_field(base="Москва", incoming="Пермь") == "conflict"


def test_classify_field_empty_incoming_is_noop():
    assert classify_field(base="Москва", incoming=None) == "noop"
    assert classify_field(base="Москва", incoming="") == "noop"
    assert classify_field(base="Москва", incoming="   ") == "noop"


def test_match_contact_by_normalized_name():
    base = [{"id": "x", "name": "Иван Петров"}, {"id": "y", "name": "Анна Смирнова"}]
    assert match_contact(base, "иван  петров") == "x"
    assert match_contact(base, "Пётр Иванов") is None


def test_match_contact_empty_name_no_match():
    """An empty/whitespace name must NOT match a base contact with empty name."""
    base = [{"id": "x", "name": ""}, {"id": "y", "name": "Анна"}]
    assert match_contact(base, "") is None
    assert match_contact(base, "   ") is None


def test_is_low_confidence_below_threshold():
    assert is_low_confidence(0.3, company_name="X") is True


def test_is_low_confidence_empty_name_is_low_regardless():
    assert is_low_confidence(0.99, company_name="") is True
    assert is_low_confidence(0.99, company_name="   ") is True


def test_is_low_confidence_above_threshold_with_name():
    assert is_low_confidence(0.9, company_name="X") is False


def test_normalized_company_key_delegates():
    """Sanity: the wrapper uses companies.utils.normalize_company_name."""
    assert normalized_company_key("ООО Ромашка") == normalized_company_key("Ромашка")
