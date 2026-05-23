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


# --- FIX-4: URL sanitisation ---

def test_javascript_website_is_stripped():
    card = ExtractedCard.model_validate({"company": {"name": "X", "website": "javascript:alert(1)"}})
    assert card.company.website is None


def test_http_website_passes():
    card = ExtractedCard.model_validate({"company": {"name": "X", "website": "https://example.com"}})
    assert card.company.website == "https://example.com"


def test_data_url_stripped():
    card = ExtractedCard.model_validate({"company": {"name": "X", "website": "data:text/html,<script>alert(1)</script>"}})
    assert card.company.website is None


def test_bare_domain_website_is_stripped():
    card = ExtractedCard.model_validate({"company": {"name": "X", "website": "example.com"}})
    assert card.company.website is None


def test_http_linkedin_passes():
    card = ExtractedCard.model_validate({
        "company": {"name": "X"},
        "contacts": [{"name": "A", "linkedin": "https://linkedin.com/in/user"}],
    })
    assert card.contacts[0].linkedin == "https://linkedin.com/in/user"


def test_javascript_linkedin_stripped():
    card = ExtractedCard.model_validate({
        "company": {"name": "X"},
        "contacts": [{"name": "A", "linkedin": "javascript:void(0)"}],
    })
    assert card.contacts[0].linkedin is None


# --- FIX-9: string truncation (permissive contract — never raise) ---

def test_strings_truncated_not_raised():
    huge = "x" * 5000
    card = ExtractedCard.model_validate({"company": {"name": huge}, "ai_brief": huge})
    assert len(card.company.name) <= 255
    assert len(card.ai_brief) <= 2000


def test_contact_strings_truncated():
    huge = "y" * 5000
    card = ExtractedCard.model_validate({
        "company": {"name": "X"},
        "contacts": [{"name": huge, "title": huge, "email": huge}],
    })
    assert len(card.contacts[0].name) <= 200
    assert len(card.contacts[0].title) <= 200
    assert len(card.contacts[0].email) <= 254
