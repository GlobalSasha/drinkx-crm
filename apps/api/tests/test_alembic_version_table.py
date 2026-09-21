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
from scripts.db_test_resources import (
    HeldAdvisoryLock,
    ProbePlan,
    UnsafeTestResource,
    asyncpg_dsn,
    plan_probe_database,
    recreate_probe_database,
)

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
PROBE_PURPOSE = "drinkx:alembic-probe"

pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="no PostgreSQL available")


def probe_plan() -> ProbePlan:
    """Decide and validate every target this fixture may touch.

    Called before anything connects. The probe name is read from the
    environment here and nowhere else: re-reading it after validation is how a
    checked value turns back into an unchecked one (review finding F1).
    """
    return plan_probe_database(
        TEST_DB_URL,
        os.environ.get("ALEMBIC_PROBE_DB", "drinkx_ci"),
        purpose=PROBE_PURPOSE,
    )


async def _run(fn, plan: ProbePlan):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(plan.probe_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(fn)
    finally:
        await engine.dispose()


@pytest.fixture
def probe_db():
    """A dedicated disposable database, validated and locked for one test.

    Order matters and is the whole point of F1: plan and validate, then take
    the lock, only then issue DDL. The lock is held on the admin database for
    the fixture's whole lifetime — a connection inside the probe database
    would block the DROP it is meant to guard — and `try/finally` covers setup
    and teardown, not just the yield.
    """
    plan = probe_plan()
    lock = HeldAdvisoryLock(asyncpg_dsn(plan.admin_url), plan.lock_key)
    if not lock.acquire():
        raise UnsafeTestResource(
            f"another run holds the probe database {plan.database!r}. It gets "
            "dropped and recreated, so the runs must not overlap."
        )
    try:
        asyncio.run(recreate_probe_database(plan))
        yield plan
    finally:
        lock.release()


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

    assert asyncio.run(_run(setup, probe_db)) == (LIMITED, 32)

    def widen(conn):
        action = ensure_version_table_width(conn)
        state, width = inspect_version_column(conn)
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        note = conn.execute(text("SELECT note FROM control_row WHERE id = 1")).scalar()
        conn.rollback()
        return action, state, width, revision, note

    action, state, width, revision, note = asyncio.run(_run(widen, probe_db))
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

    asyncio.run(_run(setup, probe_db))
    assert asyncio.run(_run(ensure_version_table_width, probe_db)) == WIDENED
    assert asyncio.run(_run(ensure_version_table_width, probe_db)) == UNCHANGED
    assert asyncio.run(_run(ensure_version_table_width, probe_db)) == UNCHANGED


@pg
def test_a_text_column_on_a_real_database_is_not_narrowed(probe_db):
    def setup(conn):
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        conn.commit()
        return inspect_version_column(conn)

    assert asyncio.run(_run(setup, probe_db)) == (UNLIMITED, None)
    assert asyncio.run(_run(ensure_version_table_width, probe_db)) == UNCHANGED

    def recheck(conn):
        state = inspect_version_column(conn)
        conn.rollback()
        return state

    assert asyncio.run(_run(recheck, probe_db)) == (UNLIMITED, None)


@pg
def test_missing_table_is_created_on_a_real_database(probe_db):
    assert asyncio.run(_run(ensure_version_table_width, probe_db)) == CREATED

    def recheck(conn):
        state = inspect_version_column(conn)
        conn.rollback()
        return state

    assert asyncio.run(_run(recheck, probe_db)) == (LIMITED, TARGET_WIDTH)

@pg
def test_a_conflicting_lock_makes_widening_fail_in_bounded_time(probe_db):
    """The scenario the original R3 acceptance asked for, on a real server.

    `ALTER TABLE ... TYPE` needs ACCESS EXCLUSIVE, which even a plain SELECT in
    an open transaction blocks. Until now only the presence of
    `SET LOCAL lock_timeout` in the emitted SQL was checked; that shows the
    statement is there, not that the wait actually ends. Here another
    transaction really holds the table.

    No assertion on how long it took: the point is that it stops at all, and
    wall-clock thresholds make tests flap on a loaded machine. The outer
    `wait_for` is a safety net, not the measurement — if the bound were
    missing, this test would hit it and fail rather than hang the suite.
    """
    import asyncpg
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    plan = probe_db

    async def scenario():
        engine = create_async_engine(plan.probe_url, poolclass=NullPool)
        holder = None
        try:
            async with engine.connect() as conn:
                await conn.run_sync(_seed_narrow_table_with_data)

            # Another transaction takes ACCESS SHARE and keeps it.
            holder = await asyncpg.connect(asyncpg_dsn(plan.probe_url), timeout=10)
            holder_tx = holder.transaction()
            await holder_tx.start()
            await holder.fetchval("SELECT count(*) FROM alembic_version")

            blocked_error = None
            async with engine.connect() as conn:
                try:
                    await conn.run_sync(
                        lambda c: ensure_version_table_width(c, lock_timeout_ms=250)
                    )
                except Exception as exc:  # noqa: BLE001 - the driver's error type is the subject
                    blocked_error = exc

            # Still narrow, and nothing was lost while the attempt failed.
            async with engine.connect() as conn:
                state_after_block = await conn.run_sync(inspect_version_column)
                revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
                note = await conn.scalar(text("SELECT note FROM control_row WHERE id = 1"))

            await holder_tx.rollback()
            await holder.close()
            holder = None

            async with engine.connect() as conn:
                action = await conn.run_sync(ensure_version_table_width)
            async with engine.connect() as conn:
                state_after_release = await conn.run_sync(inspect_version_column)
                revision_after = await conn.scalar(text("SELECT version_num FROM alembic_version"))
                note_after = await conn.scalar(text("SELECT note FROM control_row WHERE id = 1"))

            return {
                "blocked_error": blocked_error,
                "state_after_block": state_after_block,
                "revision": revision,
                "note": note,
                "action": action,
                "state_after_release": state_after_release,
                "revision_after": revision_after,
                "note_after": note_after,
            }
        finally:
            if holder is not None:
                await holder.close()
            await engine.dispose()

    async def guarded():
        # Generous: this is "it did not hang", not a performance assertion.
        return await asyncio.wait_for(scenario(), timeout=60)

    result = asyncio.run(guarded())

    assert result["blocked_error"] is not None, (
        "widening succeeded while another transaction held the table"
    )
    assert "lock" in str(result["blocked_error"]).lower(), result["blocked_error"]

    # The failed attempt changed nothing.
    assert result["state_after_block"] == (LIMITED, 32)
    assert result["revision"] == "0008_channel_connections"
    assert result["note"] == "must survive widening"

    # Once the other transaction lets go, the same call succeeds.
    assert result["action"] == WIDENED
    assert result["state_after_release"] == (LIMITED, TARGET_WIDTH)
    assert result["revision_after"] == "0008_channel_connections"
    assert result["note_after"] == "must survive widening"


def _seed_narrow_table_with_data(conn) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    )
    conn.exec_driver_sql("INSERT INTO alembic_version VALUES ('0008_channel_connections')")
    conn.exec_driver_sql("CREATE TABLE control_row (id int primary key, note text)")
    conn.exec_driver_sql("INSERT INTO control_row VALUES (1, 'must survive widening')")
    conn.commit()
