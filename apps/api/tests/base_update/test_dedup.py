from app.base_update.dedup import dedup_batch
from app.base_update.schemas import ExtractedCard


def _card(name, city=None, files=None, brief=""):
    c = ExtractedCard.model_validate({"company": {"name": name, "city": city}, "ai_brief": brief})
    return c, (files or [f"{name}.md"])


def test_same_normalized_name_merges_silently():
    groups = dedup_batch([
        _card("ООО Газпромнефть", city="Москва", files=["a.md"]),
        _card("Газпромнефть", city="Москва", files=["b.md"]),
    ])
    assert len(groups) == 1
    g = groups[0]
    assert sorted(g.source_files) == ["a.md", "b.md"]
    assert g.conflict is False


def test_same_name_diverging_field_flags_conflict():
    groups = dedup_batch([
        _card("Лукойл", city="Москва", files=["a.md"]),
        _card("Лукойл", city="Пермь", files=["b.md"]),
    ])
    assert len(groups) == 1
    assert groups[0].conflict is True
    assert groups[0].conflict_field == "city"


def test_distinct_companies_stay_separate():
    groups = dedup_batch([_card("Дикси"), _card("Перекрёсток")])
    assert len(groups) == 2


def test_primary_card_has_most_fields():
    """When merging duplicates, the card with more filled fields is .primary."""
    sparse, _ = _card("Магнит")
    rich = ExtractedCard.model_validate({
        "company": {"name": "Магнит", "city": "Краснодар", "segment": "retail", "website": "magnit.ru"},
    })
    groups = dedup_batch([(sparse, ["s.md"]), (rich, ["r.md"])])
    assert len(groups) == 1
    assert groups[0].primary.company.website == "magnit.ru"


def test_empty_input_returns_empty_list():
    assert dedup_batch([]) == []


def test_empty_company_name_groups_together():
    """Cards with no company name end up under the empty key — still produce one group, no crash."""
    nameless1 = ExtractedCard.model_validate({"company": {}})
    nameless2 = ExtractedCard.model_validate({"company": {"name": ""}})
    groups = dedup_batch([(nameless1, ["a.md"]), (nameless2, ["b.md"])])
    assert len(groups) == 1
    assert groups[0].normalized_name == ""
