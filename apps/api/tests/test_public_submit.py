"""Tests for the public WebForms submit + embed.js endpoints
— Sprint 2.2 G2.

Mock-only. SQLAlchemy stubbed at import time; Redis is replaced with
an AsyncMock per-test. The submit handler is invoked directly (no
TestClient) so we can isolate the FastAPI dependency injection from
the path-aware CORS middleware which doesn't matter for the unit
tests.
"""
from __future__ import annotations

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


def _stub_redis():
    """`app.import_export.redis_bytes` (transitively imported by
    public_routers) does `import redis.asyncio`. Local dev boxes
    don't always have the `redis` package — stub it so the module
    can load without erroring."""
    if "redis" in sys.modules:
        return
    redis_mod = ModuleType("redis")
    redis_async = ModuleType("redis.asyncio")
    redis_async.Redis = object
    redis_async.from_url = lambda *a, **kw: MagicMock()
    redis_mod.asyncio = redis_async
    sys.modules["redis"] = redis_mod
    sys.modules["redis.asyncio"] = redis_async


_stub_redis()

import app.forms.embed as embed_mod  # noqa: E402
import app.forms.public_routers as public_mod  # noqa: E402
import app.forms.rate_limit as rl_mod  # noqa: E402


WS = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_form(*, slug="test-form-abc123", is_active=True, name="Test Form",
               redirect_url="https://example.com/thanks"):
    return type("WebFormStub", (), {
        "id": uuid.uuid4(),
        "workspace_id": WS,
        "slug": slug,
        "name": name,
        "fields_json": [
            {"key": "company_name", "label": "Компания", "type": "text", "required": True},
            {"key": "email", "label": "Email", "type": "email", "required": False},
        ],
        "target_pipeline_id": None,
        "target_stage_id": None,
        "redirect_url": redirect_url,
        "is_active": is_active,
        "submissions_count": 0,
    })()


def _make_lead(company_name="Stars Coffee"):
    return type("LeadStub", (), {
        "id": uuid.uuid4(),
        "workspace_id": WS,
        "company_name": company_name,
    })()


def _make_request(*, headers=None, client_host="1.2.3.4"):
    """Lightweight Request-shaped stub for the submit handler.
    public_routers reads .headers, .url.path, .client.host — provide
    those, leave the rest as MagicMock."""
    req = MagicMock()
    req.headers = headers or {}
    req.client = MagicMock()
    req.client.host = client_host
    return req


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    # The admin-notify path queries User.id WHERE workspace+role —
    # return an empty result by default so notification is a no-op.
    empty = MagicMock()
    empty.all = MagicMock(return_value=[])
    db.execute.return_value = empty
    return db


# ===========================================================================
# 1. Happy path — 200 + redirect
# ===========================================================================

@pytest.mark.asyncio
async def test_submit_returns_ok_and_redirect():
    """Active form, lead created, FormSubmission staged, response carries
    the form's redirect URL."""
    form = _make_form()
    lead = _make_lead()
    db = _make_db()
    req = _make_request(headers={"referer": "https://www.drinkx.ru/"})

    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock()

    with patch("app.forms.public_routers.get_bytes_redis", return_value=fake_redis), \
         patch("app.forms.repositories.get_by_slug", new=AsyncMock(return_value=form)), \
         patch.object(public_mod, "create_lead_from_submission",
                      new=AsyncMock(return_value=lead)), \
         patch.object(public_mod, "FormSubmission", lambda **kw: MagicMock(**kw)), \
         patch("app.forms.repositories.increment_submissions_count",
               new=AsyncMock()):
        result = await public_mod.submit_form(
            slug=form.slug,
            request=req,
            payload={"company_name": "Stars Coffee", "email": "x@y.io"},
            db=db,
        )

    assert result == {"ok": True, "redirect": form.redirect_url}
    # Submission row added; counter incremented (via patched fn)
    db.add.assert_called()


# ===========================================================================
# 2. Inactive form → 410
# ===========================================================================

@pytest.mark.asyncio
async def test_submit_inactive_form_returns_410():
    """Soft-deleted forms return 410 Gone with a clear message."""
    from fastapi import HTTPException

    form = _make_form(is_active=False)
    db = _make_db()
    req = _make_request()

    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock()

    with patch("app.forms.public_routers.get_bytes_redis", return_value=fake_redis), \
         patch("app.forms.repositories.get_by_slug", new=AsyncMock(return_value=form)):
        with pytest.raises(HTTPException) as exc_info:
            await public_mod.submit_form(
                slug=form.slug,
                request=req,
                payload={"company_name": "Stars"},
                db=db,
            )
    assert exc_info.value.status_code == 410


# ===========================================================================
# 3. Unknown slug → 404
# ===========================================================================

@pytest.mark.asyncio
async def test_submit_unknown_slug_returns_404():
    from fastapi import HTTPException

    db = _make_db()
    req = _make_request()

    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock()

    with patch("app.forms.public_routers.get_bytes_redis", return_value=fake_redis), \
         patch("app.forms.repositories.get_by_slug", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc_info:
            await public_mod.submit_form(
                slug="ghost-form",
                request=req,
                payload={"company_name": "X"},
                db=db,
            )
    assert exc_info.value.status_code == 404


# ===========================================================================
# 4. Rate limit blocks at 11
# ===========================================================================

@pytest.mark.asyncio
async def test_rate_limit_blocks_on_11th_request():
    """When INCR returns 11 (one over the 10/min limit), the handler
    raises 429 before doing any DB work."""
    from fastapi import HTTPException

    db = _make_db()
    req = _make_request()

    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(return_value=11)
    fake_redis.expire = AsyncMock()

    with patch("app.forms.public_routers.get_bytes_redis", return_value=fake_redis), \
         patch("app.forms.repositories.get_by_slug", new=AsyncMock()) as gbs:
        with pytest.raises(HTTPException) as exc_info:
            await public_mod.submit_form(
                slug="anything",
                request=req,
                payload={},
                db=db,
            )
    assert exc_info.value.status_code == 429
    # Form lookup never ran — rate limit short-circuits before DB
    gbs.assert_not_called()


# ===========================================================================
# 5. Rate limit fails open on Redis error
# ===========================================================================

@pytest.mark.asyncio
async def test_rate_limit_fails_open_on_redis_error():
    """Redis connection error → check_rate_limit returns True. Better to
    accept a few extra spam submissions than to block real customers
    while Redis is bouncing."""
    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(side_effect=ConnectionError("redis down"))

    allowed = await rl_mod.check_rate_limit(
        fake_redis, ip="1.2.3.4", slug="any", limit=10
    )
    assert allowed is True


# ===========================================================================
# 6. UTM extracted from body
# ===========================================================================

@pytest.mark.asyncio
async def test_utm_extracted_from_body():
    """utm_* keys in the submission body land in FormSubmission.utm_json."""
    form = _make_form()
    lead = _make_lead()
    db = _make_db()
    req = _make_request()

    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock()

    submission_kwargs: list[dict] = []

    def _fs_spy(**kw):
        submission_kwargs.append(kw)
        return MagicMock(**kw)

    with patch("app.forms.public_routers.get_bytes_redis", return_value=fake_redis), \
         patch("app.forms.repositories.get_by_slug", new=AsyncMock(return_value=form)), \
         patch.object(public_mod, "create_lead_from_submission",
                      new=AsyncMock(return_value=lead)), \
         patch.object(public_mod, "FormSubmission", _fs_spy), \
         patch("app.forms.repositories.increment_submissions_count",
               new=AsyncMock()):
        await public_mod.submit_form(
            slug=form.slug,
            request=req,
            payload={
                "company_name": "Stars Coffee",
                "utm_source": "google",
                "utm_medium": "cpc",
                "utm_campaign": "spring-2026",
            },
            db=db,
        )

    assert len(submission_kwargs) == 1
    utm = submission_kwargs[0]["utm_json"]
    assert utm["utm_source"] == "google"
    assert utm["utm_medium"] == "cpc"
    assert utm["utm_campaign"] == "spring-2026"


# ===========================================================================
# 7. Source domain extracted from Referer (www. stripped)
# ===========================================================================

def test_source_domain_extracted_from_referer():
    """`https://www.drinkx.ru/coffee` → 'drinkx.ru'. www. prefix is
    removed so two managers comparing source-domain analytics across
    "www" and "non-www" landing-page variants see the same bucket."""
    req = _make_request(
        headers={"referer": "https://www.drinkx.ru/coffee?ref=footer"}
    )
    domain = public_mod._source_domain(req)
    assert domain == "drinkx.ru"

    # Also test without www. — should pass through
    req2 = _make_request(
        headers={"referer": "https://lp.drinkx.ru/promo"}
    )
    assert public_mod._source_domain(req2) == "lp.drinkx.ru"

    # Empty / missing referer — None
    assert public_mod._source_domain(_make_request()) is None


# ===========================================================================
# 8. company_name fallback
# ===========================================================================

@pytest.mark.asyncio
async def test_company_name_fallback_to_form_name():
    """Payload missing company_name and no source_domain → Lead falls
    back to «Заявка с формы {form.name}» so we never persist a Lead
    with empty company_name (NOT NULL on the column)."""
    from app.forms.lead_factory import create_lead_from_submission

    form = _make_form(name="Кофе для офиса")

    lead_kwargs: list[dict] = []

    class _LeadSpy:
        def __init__(self, **kw):
            lead_kwargs.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()

    db = _make_db()

    pipelines_module = ModuleType("app.pipelines")
    repos_module = ModuleType("app.pipelines.repositories")
    repos_module.get_default_first_stage = AsyncMock(return_value=None)
    pipelines_module.repositories = repos_module

    with patch("app.forms.lead_factory.Lead", _LeadSpy), \
         patch.dict(sys.modules, {
             "app.pipelines": pipelines_module,
             "app.pipelines.repositories": repos_module,
         }):
        lead = await create_lead_from_submission(
            db,
            form=form,
            payload={"email": "x@y.io"},  # no company_name!
            source_domain=None,
        )

    assert len(lead_kwargs) == 1
    assert lead_kwargs[0]["company_name"] == "Заявка с формы Кофе для офиса"
    assert lead.company_name == "Заявка с формы Кофе для офиса"


# ===========================================================================
# 9. embed.js contains slug
# ===========================================================================

def test_embed_js_contains_slug():
    """The generated JS carries the form's slug (in CONFIG, in the mount
    ID, in the once-loaded guard) — proof that the script is wired to
    the right form definition."""
    form = _make_form(slug="forma-dlya-horeca-a3x9kp", name="Форма для HoReCa")
    js = embed_mod.generate_embed_js(form, api_base_url="https://crm.drinkx.tech")

    assert "forma-dlya-horeca-a3x9kp" in js
    # Submit URL points at the public endpoint
    assert "/api/public/forms/forma-dlya-horeca-a3x9kp/submit" in js
    # Once-loaded guard (`__drinkxFormLoaded_<safe-id>`) survives the
    # hyphen → underscore transform in _safe_id
    assert "__drinkxFormLoaded_forma_dlya_horeca_a3x9kp" in js
