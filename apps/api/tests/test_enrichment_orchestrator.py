"""Tests for Sprint 1.3.C — Research Agent orchestrator.

All network calls (LLM + sources) are monkeypatched.
We avoid importing sqlalchemy-dependent modules at collection time by using
lazy imports inside each test/fixture.

The orchestrator itself imports sqlalchemy, so we mock the entire DB layer
with AsyncMock and patch sqlalchemy imports early via conftest or sys.modules.
"""
from __future__ import annotations

import json
import sys
import uuid
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal sqlalchemy stub — installed BEFORE any app code is imported
# ---------------------------------------------------------------------------

_SA_STUBBED = "sqlalchemy" not in sys.modules


def _stub_sqlalchemy():
    """Install minimal sqlalchemy stubs for ORM-dependent imports."""
    if "sqlalchemy" in sys.modules:
        return

    def _noop(*a, **kw):
        return None

    class _Callable:
        """Stub that returns itself from any call or attribute access — supports method chaining."""
        _instance = None

        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True

    sa = ModuleType("sqlalchemy")
    for name in (
        "Column", "ForeignKey", "Integer", "String", "Text", "JSON",
        "Numeric", "DateTime", "Boolean", "Index", "select",
        "desc", "false", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
    ):
        setattr(sa, name, _Callable)

    # func needs to be an instance that returns a Callable from any attribute access
    class _Func:
        def __getattr__(self, name):
            return _Callable

    sa.func = _Func()

    sa_ext = ModuleType("sqlalchemy.ext")
    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_dialects = ModuleType("sqlalchemy.dialects")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")

    class _Mapped:
        def __class_getitem__(cls, item): return cls

    class _DeclarativeBase:
        metadata = MagicMock()

    sa_orm.DeclarativeBase = _DeclarativeBase
    sa_orm.Mapped = _Mapped
    sa_orm.mapped_column = _noop
    sa_orm.relationship = _Callable()
    sa_orm.selectinload = _Callable()

    sa_pg.UUID = _Callable
    sa_pg.JSON = _Callable

    sa_async.AsyncSession = object
    sa_async.async_sessionmaker = _Callable
    sa_async.create_async_engine = _Callable
    sa_async.AsyncEngine = object

    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = sa_ext
    sys.modules["sqlalchemy.ext.asyncio"] = sa_async
    sys.modules["sqlalchemy.dialects"] = sa_dialects
    sys.modules["sqlalchemy.dialects.postgresql"] = sa_pg
    sys.modules["sqlalchemy.orm"] = sa_orm

    # Also stub asyncpg to avoid conftest probe
    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = ModuleType("asyncpg")


_stub_sqlalchemy()

# ---------------------------------------------------------------------------
# Imports after stubbing
# ---------------------------------------------------------------------------

from app.enrichment.providers.base import CompletionResult, LLMServerError  # noqa: E402
from app.enrichment.schemas import ResearchOutput  # noqa: E402
from app.enrichment.sources.base import SourceResult  # noqa: E402
from app.enrichment.orchestrator import (  # noqa: E402
    _build_queries,
    _format_brave_block,
    _format_hh_block,
    run_enrichment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_run(lead_id=None):
    run = MagicMock()
    run.id = uuid.uuid4()
    run.lead_id = lead_id or uuid.uuid4()
    run.status = "running"
    run.provider = None
    run.model = None
    run.prompt_tokens = 0
    run.completion_tokens = 0
    run.cost_usd = Decimal("0")
    run.duration_ms = 0
    run.sources_used = []
    run.error = None
    run.result_json = None
    run.finished_at = None
    return run


def _make_lead(company_name="ООО Тест", city="Москва", segment="HoReCa", website=None):
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.company_name = company_name
    lead.city = city
    lead.segment = segment
    lead.website = website
    lead.ai_data = None
    lead.fit_score = None
    return lead


def _make_db(run, lead):
    db = AsyncMock()
    call_count = [0]

    async def _execute(stmt, *args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = run
        else:
            result.scalar_one_or_none.return_value = lead
        return result

    db.execute = _execute
    db.commit = AsyncMock()
    return db


def _valid_research_json(**overrides) -> str:
    data = {
        "company_profile": "Отличная компания",
        "network_scale": "50-200",
        "geography": "Москва",
        "formats": "офис",
        "coffee_signals": "есть кофе",
        "growth_signals": ["рост 30%"],
        "risk_signals": [],
        "decision_maker_hints": [],
        "fit_score": 7.5,
        "next_steps": ["позвонить"],
        "urgency": "high",
        "sources_used": ["brave", "hh"],
        "notes": "",
    }
    data.update(overrides)
    return json.dumps(data)


def _sr(source: str, items: list | None = None) -> SourceResult:
    return SourceResult(source=source, query="q", items=items or [], error="")


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_enrichment_happy_path(monkeypatch):
    """succeeded + lead.ai_data populated + cost/tokens captured."""
    run = _make_run()
    lead = _make_lead()
    db = _make_db(run, lead)

    completion = CompletionResult(
        text=_valid_research_json(),
        model="test-model",
        provider="mimo",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.002,
    )
    monkeypatch.setattr("app.enrichment.orchestrator.BraveSearch.fetch", AsyncMock(return_value=_sr("brave", [{"title": "X", "url": "u", "description": "d"}])))
    monkeypatch.setattr("app.enrichment.orchestrator.HHRu.fetch", AsyncMock(return_value=_sr("hh", [{"title": "j", "company": "X", "city": "M", "url": "u"}])))
    monkeypatch.setattr("app.enrichment.orchestrator.complete_with_fallback", AsyncMock(return_value=completion))

    await run_enrichment(db=db, run_id=run.id)

    assert run.status == "succeeded"
    assert run.provider == "mimo"
    assert run.prompt_tokens == 100
    assert run.completion_tokens == 50
    assert run.cost_usd == Decimal("0.002")
    assert run.finished_at is not None
    assert lead.ai_data["company_profile"] == "Отличная компания"
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_run_enrichment_handles_invalid_json_from_llm(monkeypatch):
    """Falls back to ResearchOutput() defaults with raw text in notes."""
    run = _make_run()
    lead = _make_lead()
    db = _make_db(run, lead)

    completion = CompletionResult(text="NOT JSON", model="m", provider="mimo", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)
    monkeypatch.setattr("app.enrichment.orchestrator.BraveSearch.fetch", AsyncMock(return_value=_sr("brave")))
    monkeypatch.setattr("app.enrichment.orchestrator.HHRu.fetch", AsyncMock(return_value=_sr("hh")))
    monkeypatch.setattr("app.enrichment.orchestrator.complete_with_fallback", AsyncMock(return_value=completion))

    await run_enrichment(db=db, run_id=run.id)

    assert run.status == "succeeded"
    assert "NOT JSON" in lead.ai_data["notes"]


@pytest.mark.asyncio
async def test_run_enrichment_marks_failed_when_provider_chain_exhausted(monkeypatch):
    """All providers raise → status=failed, error populated."""
    run = _make_run()
    lead = _make_lead()
    db = _make_db(run, lead)

    monkeypatch.setattr("app.enrichment.orchestrator.BraveSearch.fetch", AsyncMock(return_value=_sr("brave")))
    monkeypatch.setattr("app.enrichment.orchestrator.HHRu.fetch", AsyncMock(return_value=_sr("hh")))
    monkeypatch.setattr(
        "app.enrichment.orchestrator.complete_with_fallback",
        AsyncMock(side_effect=LLMServerError("all down", provider="factory")),
    )

    await run_enrichment(db=db, run_id=run.id)

    assert run.status == "failed"
    assert "LLMServerError" in run.error
    assert run.finished_at is not None
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_run_enrichment_uses_lead_website_for_web_fetch(monkeypatch):
    """WebFetch.fetch called when lead.website is set."""
    run = _make_run()
    lead = _make_lead(website="https://example.com")
    db = _make_db(run, lead)

    web_mock = AsyncMock(return_value=_sr("web_fetch", [{"url": "https://example.com", "title": "E", "text": "t", "status": 200, "content_type": "text/html"}]))
    completion = CompletionResult(text=_valid_research_json(), model="m", provider="mimo", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)

    monkeypatch.setattr("app.enrichment.orchestrator.BraveSearch.fetch", AsyncMock(return_value=_sr("brave")))
    monkeypatch.setattr("app.enrichment.orchestrator.HHRu.fetch", AsyncMock(return_value=_sr("hh")))
    monkeypatch.setattr("app.enrichment.orchestrator.WebFetch.fetch", web_mock)
    monkeypatch.setattr("app.enrichment.orchestrator.complete_with_fallback", AsyncMock(return_value=completion))

    await run_enrichment(db=db, run_id=run.id)

    web_mock.assert_called_once_with("https://example.com", use_cache=True)


@pytest.mark.asyncio
async def test_run_enrichment_skips_web_fetch_when_no_website(monkeypatch):
    """WebFetch.fetch NOT called when lead.website is None."""
    run = _make_run()
    lead = _make_lead(website=None)
    db = _make_db(run, lead)

    web_mock = AsyncMock()
    completion = CompletionResult(text=_valid_research_json(), model="m", provider="mimo", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)

    monkeypatch.setattr("app.enrichment.orchestrator.BraveSearch.fetch", AsyncMock(return_value=_sr("brave")))
    monkeypatch.setattr("app.enrichment.orchestrator.HHRu.fetch", AsyncMock(return_value=_sr("hh")))
    monkeypatch.setattr("app.enrichment.orchestrator.WebFetch.fetch", web_mock)
    monkeypatch.setattr("app.enrichment.orchestrator.complete_with_fallback", AsyncMock(return_value=completion))

    await run_enrichment(db=db, run_id=run.id)

    web_mock.assert_not_called()


@pytest.mark.asyncio
async def test_run_enrichment_aggregates_sources_used(monkeypatch):
    """sources_used includes all sources that returned items."""
    run = _make_run()
    lead = _make_lead(website="https://example.com")
    db = _make_db(run, lead)

    completion = CompletionResult(text=_valid_research_json(**{"sources_used": []}), model="m", provider="mimo", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)

    monkeypatch.setattr("app.enrichment.orchestrator.BraveSearch.fetch", AsyncMock(return_value=_sr("brave", [{"title": "X", "url": "u", "description": "d"}])))
    monkeypatch.setattr("app.enrichment.orchestrator.HHRu.fetch", AsyncMock(return_value=_sr("hh", [{"title": "j", "company": "X", "city": "M", "url": "u"}])))
    monkeypatch.setattr("app.enrichment.orchestrator.WebFetch.fetch", AsyncMock(return_value=_sr("web_fetch", [{"url": "https://example.com", "title": "E", "text": "t", "status": 200, "content_type": "text/html"}])))
    monkeypatch.setattr("app.enrichment.orchestrator.complete_with_fallback", AsyncMock(return_value=completion))

    await run_enrichment(db=db, run_id=run.id)

    assert "brave" in run.sources_used
    assert "hh" in run.sources_used
    assert "web_fetch" in run.sources_used


# ---------------------------------------------------------------------------
# Query builder unit tests
# ---------------------------------------------------------------------------

def test_query_builder_includes_company_and_city():
    lead = _make_lead(company_name="ООО Ромашка", city="Казань")
    queries = _build_queries(lead)
    assert len(queries) == 3
    assert any("ООО Ромашка" in q for q in queries)
    assert any("Казань" in q for q in queries)


def test_query_builder_handles_missing_city():
    lead = _make_lead(company_name="Рога и Копыта", city=None)
    lead.city = None
    queries = _build_queries(lead)
    assert all("Рога и Копыта" in q for q in queries)


# ---------------------------------------------------------------------------
# Synthesis prompt block helpers
# ---------------------------------------------------------------------------

def test_synthesis_prompt_includes_brave_and_hh_blocks():
    brave_result = _sr("brave", [{"title": "Found Co", "url": "https://found.co", "description": "drinks"}])
    hh_result = _sr("hh", [{"title": "Barista", "company": "Found Co", "city": "SPb", "url": "https://hh.ru/1"}])

    brave_block = _format_brave_block([brave_result])
    hh_block = _format_hh_block(hh_result)

    assert "Found Co" in brave_block
    assert "https://found.co" in brave_block
    assert "Barista" in hh_block


def test_synthesis_prompt_empty_when_no_results():
    assert "нет" in _format_brave_block([])
    assert "нет" in _format_hh_block(_sr("hh"))
