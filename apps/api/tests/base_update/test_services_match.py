from types import SimpleNamespace

from app.base_update.services import CompanyMatch, _match_from_rows


def _row(id_, name):
    """Cheap stand-in for an ORM Company row — only the .id and .name we use."""
    return SimpleNamespace(id=id_, name=name)


def test_empty_name_is_create():
    assert _match_from_rows("", []).action == "create"
    assert _match_from_rows("   ", []).action == "create"


def test_no_rows_is_create():
    m = _match_from_rows("Несуществующая Компания", [])
    assert m.action == "create"
    assert m.company_id is None
    assert m.candidates == []


def test_one_row_is_update():
    row = _row("c1", "ООО Ромашка")
    m = _match_from_rows("Ромашка", [row])
    assert m.action == "update"
    assert m.company_id == "c1"
    assert m.candidates == []


def test_many_rows_is_ambiguous_with_candidates():
    rows = [_row("a", "Лукойл"), _row("b", "Лукойл (Москва)")]
    m = _match_from_rows("Лукойл", rows)
    assert m.action == "ambiguous"
    assert m.company_id is None
    assert {c["id"] for c in m.candidates} == {"a", "b"}
    assert {c["name"] for c in m.candidates} == {"Лукойл", "Лукойл (Москва)"}
