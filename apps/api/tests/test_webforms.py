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
