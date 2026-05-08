"""Tests for app.forms slug + service helpers — Sprint 2.2 G1.

Mock-only. Slug tests are pure stdlib; service tests stub sqlalchemy at
import time so the ORM imports don't drag the declarative base in.
"""
from __future__ import annotations

import re
import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub
# ---------------------------------------------------------------------------

def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return

    class _Callable:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True
        def __lt__(self, other): return _Callable()
        def __le__(self, other): return _Callable()
        def __gt__(self, other): return _Callable()
        def __ge__(self, other): return _Callable()

    sa = ModuleType("sqlalchemy")
    for name in (
        "Column", "ForeignKey", "Integer", "String", "Text", "JSON",
        "Numeric", "DateTime", "Boolean", "Index", "select", "func",
        "desc", "false", "true", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
        "Date",
    ):
        setattr(sa, name, _Callable)

    class _Func:
        def __getattr__(self, name):
            return _Callable
    sa.func = _Func()

    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")
    sa_ext = ModuleType("sqlalchemy.ext")
    sa_dialects = ModuleType("sqlalchemy.dialects")
    sa_exc = ModuleType("sqlalchemy.exc")

    class _Mapped:
        def __class_getitem__(cls, item): return cls

    class _DeclarativeBase:
        metadata = MagicMock()

    sa_orm.DeclarativeBase = _DeclarativeBase
    sa_orm.Mapped = _Mapped
    sa_orm.mapped_column = lambda *a, **kw: _Callable()
    sa_orm.relationship = _Callable()
    sa_orm.selectinload = _Callable()
    sa_orm.joinedload = _Callable()

    sa_pg.UUID = _Callable
    sa_pg.JSON = _Callable
    sa_async.AsyncSession = object
    sa_async.async_sessionmaker = _Callable
    sa_async.create_async_engine = _Callable
    sa_async.AsyncEngine = object

    class _IntegrityError(Exception):
        pass

    sa_exc.IntegrityError = _IntegrityError

    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = sa_ext
    sys.modules["sqlalchemy.ext.asyncio"] = sa_async
    sys.modules["sqlalchemy.dialects"] = sa_dialects
    sys.modules["sqlalchemy.dialects.postgresql"] = sa_pg
    sys.modules["sqlalchemy.orm"] = sa_orm
    sys.modules["sqlalchemy.exc"] = sa_exc

    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = ModuleType("asyncpg")


_stub_sqlalchemy()

from app.forms import services as svc_mod  # noqa: E402
from app.forms.slug import generate_slug  # noqa: E402


WS = uuid.uuid4()


# ---------------------------------------------------------------------------
# Lead-factory fixtures — Sprint 2.2 G4
#
# The lead_factory module constructs Lead and Activity ORM objects. Under
# the sqlalchemy stub above, those classes inherit from a stub
# DeclarativeBase whose default __init__ rejects kwargs. We swap them
# (and the local pipelines repo import) for spy classes that capture
# constructor kwargs into a list — enough to assert which Activity rows
# would be persisted.
# ---------------------------------------------------------------------------

def _make_lead_factory_env():
    """Build the patches + capture lists needed to drive
    create_lead_from_submission without a real DB. Returns (lead_kw_list,
    activity_kw_list, contextmanager-stack-builder)."""
    leads_captured: list[dict] = []
    activities_captured: list[dict] = []

    class _LeadSpy:
        def __init__(self, **kw):
            leads_captured.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()

    class _ActivitySpy:
        def __init__(self, **kw):
            activities_captured.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)

    # Always feed the factory a stage tuple so it never tries to hit
    # the real pipelines repo when target_* is None.
    async def fake_get_default_first_stage(_session, _ws):
        return (uuid.uuid4(), uuid.uuid4())

    from app.forms import lead_factory as lf_mod

    patches = [
        patch.object(lf_mod, "Lead", _LeadSpy),
        patch.object(lf_mod, "Activity", _ActivitySpy),
        patch(
            "app.pipelines.repositories.get_default_first_stage",
            new=fake_get_default_first_stage,
        ),
    ]
    return leads_captured, activities_captured, patches


def _make_form(**overrides):
    """Mock WebForm instance for lead_factory. We don't construct the
    real ORM class — the factory only reads attributes."""
    form = MagicMock()
    form.workspace_id = WS
    form.target_pipeline_id = uuid.uuid4()
    form.target_stage_id = uuid.uuid4()
    form.name = "Тестовая форма"
    form.slug = "testovaya-forma-abc123"
    for k, v in overrides.items():
        setattr(form, k, v)
    return form


def _make_session():
    """AsyncSession mock — sync .add(), async .flush()."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


# ===========================================================================
# Slug
# ===========================================================================

def test_generate_slug_ru_transliteration():
    """RU input lands on the canonical translit + lowercase + hyphen
    join. Suffix is variable so we strip it before comparing the base."""
    slug = generate_slug("Форма для HoReCa")
    base = slug.rsplit("-", 1)[0]  # drop the random 6-char suffix
    assert base == "forma-dlya-horeca"


def test_generate_slug_has_random_suffix():
    """Two calls with the same name produce different slugs because of
    the cryptographic 6-char suffix. Practically eliminates collision."""
    a = generate_slug("Test Form")
    b = generate_slug("Test Form")
    assert a != b
    suffix_a = a.rsplit("-", 1)[-1]
    suffix_b = b.rsplit("-", 1)[-1]
    assert len(suffix_a) == 6
    assert len(suffix_b) == 6


def test_generate_slug_url_safe_chars_only():
    """Output is restricted to [a-z0-9-]. No accidental Cyrillic / unicode
    leaks through, no spaces, no underscores. Punctuation collapses to
    hyphens; emoji-only input falls back to suffix-only slug."""
    slug = generate_slug("Привет, мир! 2026 — best_form")
    assert re.fullmatch(r"[a-z0-9-]+", slug), f"non-url-safe chars in {slug!r}"
    assert "_" not in slug
    assert " " not in slug

    # Emoji-only edge case — should still produce a non-empty slug
    # (just the suffix). Important so the unique slug column never sees ''.
    suffix_only = generate_slug("🎉🎉")
    assert re.fullmatch(r"[a-z0-9]{6}", suffix_only), f"unexpected: {suffix_only!r}"


# ===========================================================================
# Service
# ===========================================================================

@pytest.mark.asyncio
async def test_create_form_generates_slug():
    """create_form auto-derives the slug from name and persists via the
    repo. Returned form carries a slug, its base matches the
    transliterated name, and the random suffix is appended."""
    db = AsyncMock()
    user_id = uuid.uuid4()
    captured: list[dict] = []

    class _WebFormSpy:
        def __init__(self, **kw):
            captured.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()

    # Patch repo.create directly — that's the surface create_form calls.
    async def fake_create(session, **kwargs):
        return _WebFormSpy(**kwargs)

    with patch("app.forms.repositories.create", new=fake_create):
        form = await svc_mod.create_form(
            db,
            workspace_id=WS,
            user_id=user_id,
            name="Тест форма",
            fields_json=[],
        )

    assert form.slug.startswith("test-forma-") or form.slug.startswith("test-")
    assert form.workspace_id == WS
    assert form.created_by == user_id
    assert form.name == "Тест форма"


@pytest.mark.asyncio
async def test_get_form_wrong_workspace_raises_404():
    """Cross-workspace lookups return None from the repo → service raises
    WebFormNotFound, which the router maps to HTTP 404."""
    db = AsyncMock()

    async def fake_get_by_id(session, **kwargs):
        return None  # row exists in another workspace, but not this one

    with patch("app.forms.repositories.get_by_id", new=fake_get_by_id):
        with pytest.raises(svc_mod.WebFormNotFound):
            await svc_mod.get_form_or_404(
                db,
                form_id=uuid.uuid4(),
                workspace_id=WS,
            )


@pytest.mark.asyncio
async def test_list_forms_scoped_to_workspace():
    """list_for_workspace passes the caller's workspace_id straight
    through — never an arbitrary value. The repo function receives it
    via kwargs and other workspaces' rows can't leak into the page."""
    from app.forms import repositories as repo_mod

    captured: dict = {}

    async def fake_list(session, **kwargs):
        captured.update(kwargs)
        return [], 0

    with patch.object(repo_mod, "list_for_workspace", new=fake_list):
        rows, total = await repo_mod.list_for_workspace(
            AsyncMock(),
            workspace_id=WS,
            page=1,
            page_size=20,
        )

    assert captured["workspace_id"] == WS
    assert captured["page"] == 1
    assert captured["page_size"] == 20
    assert rows == []
    assert total == 0


# ===========================================================================
# Lead-factory: form_submission Activity — Sprint 2.2 G4
# ===========================================================================

@pytest.mark.asyncio
async def test_form_submission_activity_created():
    """Every public-form submission lands at least one
    Activity(type='form_submission') on the new lead, carrying form_name,
    form_slug, source_domain and utm. This is the canonical provenance
    record the Activity Feed renders as «Заявка с формы»."""
    from app.forms import lead_factory as lf_mod

    leads, activities, patches = _make_lead_factory_env()
    form = _make_form(name="Лендинг QSR", slug="lending-qsr-xx9911")
    session = _make_session()

    with patches[0], patches[1], patches[2]:
        lead = await lf_mod.create_lead_from_submission(
            session,
            form=form,
            payload={"company": "ООО Кофейня"},
            source_domain="example.ru",
            utm={"utm_source": "google", "utm_campaign": "qsr-q4"},
        )

    assert lead is not None
    assert len(leads) == 1, "exactly one Lead should be created"

    fs = [a for a in activities if a.get("type") == "form_submission"]
    assert len(fs) == 1, "exactly one form_submission activity expected"
    payload = fs[0]["payload_json"]
    assert payload["form_name"] == "Лендинг QSR"
    assert payload["form_slug"] == "lending-qsr-xx9911"
    assert payload["source_domain"] == "example.ru"
    assert payload["utm"] == {"utm_source": "google", "utm_campaign": "qsr-q4"}


@pytest.mark.asyncio
async def test_notes_activity_created_when_comment_in_payload():
    """When the submitted payload carries a freeform note (RU
    «комментарий» or EN «comment»/«message»), the factory emits BOTH a
    type='comment' activity (with the surfaced text) and a separate
    type='form_submission' activity. The two are intentionally
    independent — the comment renders as plain text in the feed, the
    form_submission carries structured provenance."""
    from app.forms import lead_factory as lf_mod

    leads, activities, patches = _make_lead_factory_env()
    form = _make_form()
    session = _make_session()

    with patches[0], patches[1], patches[2]:
        await lf_mod.create_lead_from_submission(
            session,
            form=form,
            payload={
                "company": "ООО Тест",
                "comment": "Хочу узнать цены на кофейные станции",
            },
            source_domain="example.ru",
        )

    types = [a.get("type") for a in activities]
    assert "form_submission" in types
    assert "comment" in types

    comment = next(a for a in activities if a.get("type") == "comment")
    assert "Хочу узнать цены" in comment["payload_json"]["text"]
    assert comment["payload_json"]["source"] == "webform"


@pytest.mark.asyncio
async def test_no_comment_activity_when_no_notes():
    """A payload with no comment/notes/message field produces ONLY the
    form_submission activity — we don't fabricate an empty comment row,
    which would clutter the Activity Feed with «Комментарий: » that
    has nothing in it."""
    from app.forms import lead_factory as lf_mod

    leads, activities, patches = _make_lead_factory_env()
    form = _make_form()
    session = _make_session()

    with patches[0], patches[1], patches[2]:
        await lf_mod.create_lead_from_submission(
            session,
            form=form,
            payload={"company": "ООО Без Комментария", "email": "a@b.ru"},
            source_domain=None,
        )

    types = [a.get("type") for a in activities]
    assert types == ["form_submission"], (
        f"expected only form_submission, got {types!r}"
    )
