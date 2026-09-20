"""Shared pytest fixtures for the DrinkX API test suite."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

# pytest_asyncio is only needed for DB-backed async fixtures (Postgres tests).
# Pure unit tests (e.g., test_0002_b2b_models.py) should run without it.
try:
    import pytest_asyncio
    PYTEST_ASYNCIO_AVAILABLE = True
except ImportError:
    pytest_asyncio = None  # type: ignore[assignment]
    PYTEST_ASYNCIO_AVAILABLE = False

# ---------------------------------------------------------------------------
# Postgres availability probe
# ---------------------------------------------------------------------------
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)

# The session fixture below runs DROP SCHEMA public CASCADE. Check the target
# is a throwaway database BEFORE the probe opens a socket, so a stray
# production DSN never even gets connected to, let alone dropped. Failing here
# is deliberate: a misconfigured DSN must stop the run, not quietly downgrade
# it to "postgres unavailable, skipping".
from scripts.db_safety import assert_disposable  # noqa: E402
from scripts.db_safety import redact as redact_dsn  # noqa: E402
from scripts.db_safety import resolved_target  # noqa: E402
from scripts.db_test_resources import advisory_key  # noqa: E402

assert_disposable(TEST_DB_URL, purpose="API test fixtures")

# DB-required mode. CI sets REQUIRE_TEST_DB=1 so an unreachable Postgres or a
# missing async driver is a failure, not a suite that silently skips its way
# to green. Local runs default to the permissive mode.
REQUIRE_TEST_DB = os.environ.get("REQUIRE_TEST_DB", "").strip() not in ("", "0", "false", "no")

POSTGRES_AVAILABLE = False
_PROBE_ERROR: str | None = None
try:
    import asyncpg  # noqa: F401

    async def _probe() -> bool:
        global _PROBE_ERROR
        dsn = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
        try:
            conn = await asyncpg.connect(dsn, timeout=2)
            await conn.close()
            return True
        except Exception as exc:
            # Probe-only suppression: any connection failure means "not available".
            # The reason is kept so REQUIRE_TEST_DB can report it.
            _PROBE_ERROR = f"{type(exc).__name__}: {exc}"
            return False

    POSTGRES_AVAILABLE = asyncio.run(_probe())
except Exception as exc:
    _PROBE_ERROR = f"{type(exc).__name__}: {exc}"
    POSTGRES_AVAILABLE = False

if REQUIRE_TEST_DB and not POSTGRES_AVAILABLE:
    from scripts.db_safety import redact

    raise RuntimeError(
        "REQUIRE_TEST_DB is set but the test database is unusable: "
        f"{_PROBE_ERROR or 'unknown reason'} (target {redact(TEST_DB_URL)}). "
        "Refusing to report a green run from skipped database tests."
    )

if REQUIRE_TEST_DB and not PYTEST_ASYNCIO_AVAILABLE:
    raise RuntimeError(
        "REQUIRE_TEST_DB is set but pytest-asyncio is not installed, so every "
        "database-backed test would be skipped."
    )


# ---------------------------------------------------------------------------
# Database-backed coverage accounting
# ---------------------------------------------------------------------------
# "1000 passed" says nothing about whether the database tests ran. Track the
# tests that actually request a session and report their real outcomes.
_DB_BACKED_IDS: set[str] = set()
_DB_BACKED_OUTCOMES = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0}


# ---------------------------------------------------------------------------
# Pre-existing failures quarantine
# ---------------------------------------------------------------------------
# These tests were already broken when CI was first enabled (the suite had never
# run under Postgres, so the rot was invisible). Quarantined as xfail so CI gates
# NEW work while this legacy debt is fixed separately. Causes are unrelated to
# any current feature work (mocks passed into SQLAlchemy select/insert after a
# version bump, a test helper that omits workspace_id, a stale enum count, etc.).
# DO NOT add new entries — fix the test instead.
_KNOWN_PRE_EXISTING_FAILURES: set[str] = {
    # Empty — the two legacy failures were fixed in G5 of the Odoo-reuse
    # follow-up sprint:
    #   * test_inbox_matcher … high_confidence_match — the attach_to_lead path's
    #     Automation-Builder / Lead-AI-Agent fan-out is now mocked.
    #   * base_update/test_e2e … extract_match_apply — the stale `pipeline`
    #     fixture now sets the workspace default-pipeline FK + position-0 stage.
}


def pytest_collection_modifyitems(config, items):
    """Mark the quarantined legacy failures as xfail (non-strict)."""
    for item in items:
        if "db" in getattr(item, "fixturenames", ()):
            _DB_BACKED_IDS.add(item.nodeid)
        if item.nodeid in _KNOWN_PRE_EXISTING_FAILURES:
            item.add_marker(
                pytest.mark.xfail(
                    reason="pre-existing failure (legacy rot, pre-CI) — tracked for cleanup",
                    strict=False,
                )
            )


def pytest_runtest_logreport(report):
    """Record the real outcome of every database-backed test."""
    if report.nodeid not in _DB_BACKED_IDS:
        return
    if report.when == "setup" and report.skipped:
        _DB_BACKED_OUTCOMES["skipped"] += 1
    elif report.when == "call":
        if getattr(report, "wasxfail", None) is not None:
            _DB_BACKED_OUTCOMES["xfailed"] += 1
        elif report.passed:
            _DB_BACKED_OUTCOMES["passed"] += 1
        elif report.failed:
            _DB_BACKED_OUTCOMES["failed"] += 1


def pytest_terminal_summary(terminalreporter, exitstatus=None, config=None):
    """Print what the database actually covered, not just the collected total."""
    from scripts.db_safety import redact

    tr = terminalreporter
    tr.write_sep("-", "database-backed coverage")
    tr.write_line(f"target            : {redact(TEST_DB_URL)}")
    tr.write_line(f"postgres available: {POSTGRES_AVAILABLE}  (REQUIRE_TEST_DB={REQUIRE_TEST_DB})")
    tr.write_line(f"db-backed tests   : {len(_DB_BACKED_IDS)} collected, " + ", ".join(
        f"{k}={v}" for k, v in _DB_BACKED_OUTCOMES.items()
    ))
    if REQUIRE_TEST_DB and _DB_BACKED_OUTCOMES["skipped"]:
        tr.write_line(
            "WARNING: database-backed tests were skipped in DB-required mode",
            red=True,
        )


# ---------------------------------------------------------------------------
# SQLAlchemy engine + session factory (Postgres + pytest_asyncio only)
# ---------------------------------------------------------------------------
if POSTGRES_AVAILABLE and PYTEST_ASYNCIO_AVAILABLE:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    # Реестр моделей, а не отдельные домены: create_all видит только уже
    # импортированные модули, поэтому без него одиночный прогон вроде
    # `pytest tests/activity` получал обрезанную схему и падал на FK
    # contacts.company_id → companies. Реестр не тянет роутеры и Celery.
    from app.models_registry import Base

    # NullPool: never reuse a connection across event loops. pytest-asyncio runs
    # each test on a fresh function-scoped loop, so a pooled connection bound to
    # the session-loop schema fixture would raise "attached to a different loop".
    _test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    _test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False, class_=AsyncSession)

    # Two pytest processes pointed at one database will destroy each other:
    # this fixture drops the public schema, so the second run pulls the tables
    # out from under the first, which then fails with "relation ... does not
    # exist" hundreds of tests in. Observed exactly that way while generating
    # review evidence alongside a full run. A PostgreSQL advisory lock makes
    # the collision a clear, immediate error instead (review finding R3).
    # Keyed on the database name alone, not on the DSN string and not on the
    # address. The same database written with and without its default port, or
    # as `localhost` and as `127.0.0.1`, produced different keys, so two runs
    # did not exclude each other after all (findings F2 and P2-1). An advisory
    # lock is scoped to the whole server, which the connection already fixes.
    _SCHEMA_LOCK_DATABASE = resolved_target(TEST_DB_URL)[2]
    _SCHEMA_LOCK_KEY = advisory_key(_SCHEMA_LOCK_DATABASE, purpose="drinkx:test-schema")

    @pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
    async def _create_tables():
        """Create all tables once per session, drop afterwards."""
        from sqlalchemy import text

        # Held for the whole session on a connection of its own; PostgreSQL
        # releases it if this process dies, so a crashed run cannot wedge the
        # next one.
        lock_conn = await _test_engine.connect()
        got_lock = await lock_conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _SCHEMA_LOCK_KEY}
        )
        if not got_lock:
            await lock_conn.close()
            raise RuntimeError(
                "another test run already holds the schema lock on "
                f"{redact_dsn(TEST_DB_URL)}. These fixtures drop and recreate "
                "the public schema, so two runs on one database corrupt each "
                "other. Wait for the other run, or point TEST_DATABASE_URL at "
                "a different disposable database."
            )

        # DROP SCHEMA … CASCADE instead of metadata.drop_all: the leads↔contacts
        # FK cycle (leads.primary_contact_id ↔ contacts.lead_id) can't be
        # dependency-sorted for DROP. CASCADE sidesteps the ordering entirely.
        async with _test_engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            # Global search uses pg_trgm (similarity()/% operator). Prod installs
            # it via migration 0023; the create_all path needs it explicitly so
            # search tests can exercise the trgm mode.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
        try:
            yield
        finally:
            async with _test_engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
            await lock_conn.exec_driver_sql(
                f"SELECT pg_advisory_unlock({_SCHEMA_LOCK_KEY})"
            )
            await lock_conn.close()

    @pytest_asyncio.fixture
    async def db():
        """Per-test async session — rolls back after each test."""
        async with _test_session_factory() as session:
            yield session
            await session.rollback()

    @pytest_asyncio.fixture
    async def workspace(db):
        """A fresh Workspace row."""
        from app.auth.models import Workspace

        ws = Workspace(name="Test WS", plan="pro", sprint_capacity_per_week=20)
        db.add(ws)
        await db.flush()
        return ws

    @pytest_asyncio.fixture
    async def user(db, workspace):
        """Manager user in the test workspace."""
        from app.auth.models import User

        u = User(
            workspace_id=workspace.id,
            email=f"mgr-{uuid.uuid4().hex[:8]}@test.com",
            name="Manager",
            role="manager",
        )
        db.add(u)
        await db.flush()
        return u

    @pytest_asyncio.fixture
    async def admin_user(db, workspace):
        """Admin user in the test workspace."""
        from app.auth.models import User

        u = User(
            workspace_id=workspace.id,
            email=f"admin-{uuid.uuid4().hex[:8]}@test.com",
            name="Admin",
            role="admin",
        )
        db.add(u)
        await db.flush()
        return u

    @pytest_asyncio.fixture
    async def pipeline(db, workspace):
        """Default pipeline + one stage."""
        from app.pipelines.models import Pipeline, Stage

        p = Pipeline(
            workspace_id=workspace.id,
            name="Sales",
            type="sales",
            position=0,
        )
        db.add(p)
        await db.flush()

        s = Stage(
            pipeline_id=p.id,
            name="Новые",
            position=1,
            color="#aabbcc",
            rot_days=14,
        )
        db.add(s)
        await db.flush()
        return p, s
