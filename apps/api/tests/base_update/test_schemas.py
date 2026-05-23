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
