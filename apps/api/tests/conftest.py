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

POSTGRES_AVAILABLE = False
try:
    import asyncpg  # noqa: F401

    async def _probe() -> bool:
        dsn = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
        try:
            conn = await asyncpg.connect(dsn, timeout=2)
            await conn.close()
            return True
        except Exception:
            # Probe-only suppression: any connection failure means "not available"
            return False

    POSTGRES_AVAILABLE = asyncio.run(_probe())
except Exception:
    POSTGRES_AVAILABLE = False


# ---------------------------------------------------------------------------
# SQLAlchemy engine + session factory (Postgres + pytest_asyncio only)
# ---------------------------------------------------------------------------
if POSTGRES_AVAILABLE and PYTEST_ASYNCIO_AVAILABLE:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.common.models import Base

    _test_engine = create_async_engine(TEST_DB_URL, echo=False, pool_pre_ping=True)
    _test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False, class_=AsyncSession)

    @pytest_asyncio.fixture(scope="session", autouse=True)
    async def _create_tables():
        """Create all tables once per session, drop afterwards."""
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        yield
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

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
            is_default=True,
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
