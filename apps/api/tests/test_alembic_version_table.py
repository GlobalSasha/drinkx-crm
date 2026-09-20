"""Bootstrap of Alembic's version table must only act when it needs to.

Review finding R3: the first version of this code ran

    CREATE TABLE IF NOT EXISTS alembic_version (...VARCHAR(255)...);
    ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255);

on every invocation, without looking at the column first. That re-issues DDL
against an already-correct table, narrows a column someone widened further or
made unlimited, and takes an ACCESS EXCLUSIVE lock with no bound on the wait.

Two layers here. The first records the SQL against a fake connection and needs
no database. The second runs against a real, dedicated disposable database —
deliberately not `drinkx_test`, which the rest of the suite drops schemas in.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from scripts.alembic_version_table import (
    CREATED,
    LIMITED,
    MISSING,
    TARGET_WIDTH,
    UNCHANGED,
    UNLIMITED,
    WIDENED,
    ensure_version_table_width,
    inspect_version_column,
)
from scripts.db_safety import assert_disposable

from tests.conftest import POSTGRES_AVAILABLE, TEST_DB_URL

# ---------------------------------------------------------------------------
# Layer one: what SQL comes out, with no database involved
# ---------------------------------------------------------------------------


class RecordingConnection:
    """Enough of a SQLAlchemy Connection to capture what would be executed."""

    def __init__(self, state, width=None):
        self._state = state
        self._width = width
        self.statements: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, *_args, **_kwargs):
        class Result:
            def __init__(self, row):
                self._row = row

            def first(self):
                return self._row

        if self._state == MISSING:
            return Result(None)
        if self._state == UNLIMITED:
            return Result(("text", None))
        return Result(("character varying", self._width))

    def exec_driver_sql(self, sql):
        self.statements.append(" ".join(sql.split()))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    @property
    def ddl(self):
        return [s for s in self.statements if s.upper().startswith(("CREATE", "ALTER TABLE"))]


def test_no_table_yet_is_created_once_at_the_target_width():
    conn = RecordingConnection(MISSING)
    assert ensure_version_table_width(conn) == CREATED
    assert len(conn.ddl) == 1
    assert f"VARCHAR({TARGET_WIDTH})" in conn.ddl[0]
    assert conn.ddl[0].startswith("CREATE TABLE alembic_version")


def test_a_column_that_is_already_wide_enough_is_left_alone():
    conn = RecordingConnection(LIMITED, TARGET_WIDTH)
    assert ensure_version_table_width(conn) == UNCHANGED
    assert conn.ddl == []


def test_an_unlimited_column_is_never_narrowed():
    conn = RecordingConnection(UNLIMITED)
    assert ensure_version_table_width(conn) == UNCHANGED
    assert conn.ddl == []


def test_a_wider_column_is_never_narrowed():
    conn = RecordingConnection(LIMITED, TARGET_WIDTH * 4)
    assert ensure_version_table_width(conn) == UNCHANGED
    assert conn.ddl == []


def test_a_narrow_column_is_widened_once_and_under_a_lock_timeout():
    conn = RecordingConnection(LIMITED, 32)
    assert ensure_version_table_width(conn) == WIDENED
    assert len(conn.ddl) == 1
    assert conn.ddl[0].startswith("ALTER TABLE alembic_version")
    assert f"VARCHAR({TARGET_WIDTH})" in conn.ddl[0]

    # The bound must be set before the ALTER, and scoped to this transaction
    # so it does not leak onto the migration chain that follows.
    lock_stmts = [s for s in conn.statements if "lock_timeout" in s]
    assert lock_stmts, "the widening runs without bounding its lock wait"
    assert lock_stmts[0].upper().startswith("SET LOCAL")
    assert conn.statements.index(lock_stmts[0]) < conn.statements.index(conn.ddl[0])


def test_repeating_the_call_on_a_correct_table_emits_nothing():
    """The claim the review rejected: prove it with emitted SQL, not with the
    absence of `Running upgrade` in an Alembic log."""
    conn = RecordingConnection(LIMITED, TARGET_WIDTH)
    for _ in range(3):
        assert ensure_version_table_width(conn) == UNCHANGED
    assert conn.ddl == []


def test_every_branch_leaves_no_open_transaction():
    for state, width in ((MISSING, None), (LIMITED, 32), (LIMITED, TARGET_WIDTH), (UNLIMITED, None)):
        conn = RecordingConnection(state, width)
        ensure_version_table_width(conn)
        assert conn.commits + conn.rollbacks == 1, f"{state}/{width} left a transaction open"


# ---------------------------------------------------------------------------
# Layer two: a real PostgreSQL, on a database of this test's own
# ---------------------------------------------------------------------------

# Not drinkx_test: the session fixture there runs DROP SCHEMA public CASCADE,
# and two destructive users on one database is how tests corrupt each other.
PROBE_DB = os.environ.get("ALEMBIC_PROBE_DB", "drinkx_ci")

pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="no PostgreSQL available")


def _probe_url() -> str:
    base = TEST_DB_URL.rsplit("/", 1)[0]
    url = f"{base}/{PROBE_DB}"
    # Same guard the fixtures use, on this test's own target.
    assert_disposable(url, purpose="alembic version table probe")
    assert not url.endswith(f"/{TEST_DB_URL.rsplit('/', 1)[1]}"), (
        "the probe database must not be the one the rest of the suite drops schemas in"
    )
    return url


async def _recreate_probe_database() -> None:
    import asyncpg

    admin = TEST_DB_URL.rsplit("/", 1)[0].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(f"{admin}/postgres", timeout=5)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{PROBE_DB}"')
        await conn.execute(f'CREATE DATABASE "{PROBE_DB}"')
    finally:
        await conn.close()


async def _run(fn):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_probe_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(fn)
    finally:
        await engine.dispose()


@pytest.fixture
def probe_db():
    """A dedicated, freshly created disposable database for one test."""
    asyncio.run(_recreate_probe_database())
    yield
    # Left in place on purpose: dropping it here would race a parallel run, and
    # the next test recreates it anyway.


@pg
def test_an_existing_narrow_table_is_widened_and_keeps_its_revision(probe_db):
    """The scenario that was never exercised: a real varchar(32) with a row in it."""
    from sqlalchemy import text

    def setup(conn):
        conn.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
        conn.exec_driver_sql("INSERT INTO alembic_version VALUES ('0008_channel_connections')")
        conn.exec_driver_sql("CREATE TABLE control_row (id int primary key, note text)")
        conn.exec_driver_sql("INSERT INTO control_row VALUES (1, 'must survive widening')")
        conn.commit()
        return inspect_version_column(conn)

    assert asyncio.run(_run(setup)) == (LIMITED, 32)

    def widen(conn):
        action = ensure_version_table_width(conn)
        state, width = inspect_version_column(conn)
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        note = conn.execute(text("SELECT note FROM control_row WHERE id = 1")).scalar()
        conn.rollback()
        return action, state, width, revision, note

    action, state, width, revision, note = asyncio.run(_run(widen))
    assert action == WIDENED
    assert (state, width) == (LIMITED, TARGET_WIDTH)
    assert revision == "0008_channel_connections", "the stored revision was lost"
    assert note == "must survive widening", "unrelated data did not survive"


@pg
def test_a_second_call_against_the_real_table_changes_nothing(probe_db):
    def setup(conn):
        conn.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        conn.commit()
        return None

    asyncio.run(_run(setup))
    assert asyncio.run(_run(ensure_version_table_width)) == WIDENED
    assert asyncio.run(_run(ensure_version_table_width)) == UNCHANGED
    assert asyncio.run(_run(ensure_version_table_width)) == UNCHANGED


@pg
def test_a_text_column_on_a_real_database_is_not_narrowed(probe_db):
    def setup(conn):
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        conn.commit()
        return inspect_version_column(conn)

    assert asyncio.run(_run(setup)) == (UNLIMITED, None)
    assert asyncio.run(_run(ensure_version_table_width)) == UNCHANGED

    def recheck(conn):
        state = inspect_version_column(conn)
        conn.rollback()
        return state

    assert asyncio.run(_run(recheck)) == (UNLIMITED, None)


@pg
def test_missing_table_is_created_on_a_real_database(probe_db):
    assert asyncio.run(_run(ensure_version_table_width)) == CREATED

    def recheck(conn):
        state = inspect_version_column(conn)
        conn.rollback()
        return state

    assert asyncio.run(_run(recheck)) == (LIMITED, TARGET_WIDTH)
