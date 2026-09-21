"""The destructive test fixtures must decide before they act.

Review findings F1 and F2.

F1: the probe fixture composed `DROP DATABASE "<name>"` from an environment
variable and sent it, then asked whether the name was allowed. With
`ALEMBIC_PROBE_DB='evil"; DROP DATABASE drinkx_crm; --'` the statement it built
named the production database. Every negative case here is checked with a
recorder in place of the driver: nothing connects, and the point of each test
is that zero statements were produced.

F2: the advisory lock was keyed on the DSN string, so one database written two
ways got two keys and two runs did not exclude each other.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.engine import make_url

from scripts.db_safety import UnsafeDatabaseTarget, resolved_target
from scripts.db_test_resources import (
    HeldAdvisoryLock,
    UnsafeTestResource,
    advisory_key,
    asyncpg_dsn,
    plan_probe_database,
    recreate_probe_database,
    validate_database_identifier,
)

REPO_API_ROOT = Path(__file__).resolve().parents[1]
MAIN = "postgresql+asyncpg://ci:dummy@localhost:5432/drinkx_test"


class Recorder:
    """Stands in for asyncpg. Records; never executes, never connects."""

    def __init__(self):
        self.connects: list[str] = []
        self.statements: list[str] = []

    async def connect(self, dsn, **_kw):
        self.connects.append(dsn)
        recorder = self

        class Conn:
            async def execute(self, sql, *_a):
                recorder.statements.append(sql)

            async def fetchval(self, sql, *args):
                recorder.statements.append(sql)
                return True

            async def close(self):
                return None

        return Conn()


# ---------------------------------------------------------------------------
# F1 — nothing is composed or sent before the target is judged
# ---------------------------------------------------------------------------

REJECTED_NAMES = [
    pytest.param("not_disposable", id="not-on-the-allowlist"),
    pytest.param("drinkx_test", id="the-main-test-database"),
    pytest.param('evil"; DROP DATABASE drinkx_crm; --', id="quote-breaks-out-of-the-identifier"),
    pytest.param("drinkx_ci; DROP DATABASE drinkx_crm", id="statement-separator"),
    pytest.param("drinkx_ci?host=elsewhere.invalid", id="url-parameters-in-the-name"),
    pytest.param("drinkx ci", id="space"),
    pytest.param("Drinkx_CI", id="upper-case"),
    pytest.param("", id="empty"),
    pytest.param("x" * 64, id="too-long-for-an-identifier"),
    pytest.param(None, id="not-a-string"),
]


@pytest.mark.parametrize("probe_name", REJECTED_NAMES)
def test_an_unacceptable_probe_name_is_refused_before_anything_connects(probe_name):
    recorder = Recorder()

    with pytest.raises(UnsafeDatabaseTarget):
        plan = plan_probe_database(MAIN, probe_name, purpose="test")
        # Unreachable when the planning is correct. Present so that a
        # regression which lets planning through is still caught here, at the
        # recorder, instead of on a real server.
        asyncio.run(recreate_probe_database(plan, connect=recorder.connect))

    assert recorder.connects == [], "a connection was opened for a rejected target"
    assert recorder.statements == [], "a statement was composed for a rejected target"


def test_an_allowed_probe_name_is_planned_and_used_verbatim():
    plan = plan_probe_database(MAIN, "drinkx_ci", purpose="test")
    assert plan.database == "drinkx_ci"
    assert plan.probe_url.endswith("/drinkx_ci")
    assert plan.admin_url.endswith("/postgres")

    recorder = Recorder()
    asyncio.run(recreate_probe_database(plan, connect=recorder.connect))

    assert recorder.connects == [asyncpg_dsn(plan.admin_url)]
    assert recorder.statements == [
        'DROP DATABASE IF EXISTS "drinkx_ci"',
        'CREATE DATABASE "drinkx_ci"',
    ]


def test_the_validated_name_is_used_even_when_the_environment_says_otherwise(monkeypatch):
    """A checked value must not turn back into an unchecked one.

    Re-reading `ALEMBIC_PROBE_DB` after validation would hand the destructive
    step a name nobody approved, which is the shape of F1 all over again.
    """
    monkeypatch.setenv("ALEMBIC_PROBE_DB", "not_disposable")

    plan = plan_probe_database(MAIN, "drinkx_ci", purpose="test")
    assert plan.database == "drinkx_ci"
    assert plan.probe_url.endswith("/drinkx_ci")

    recorder = Recorder()
    asyncio.run(recreate_probe_database(plan, connect=recorder.connect))
    assert recorder.statements == [
        'DROP DATABASE IF EXISTS "drinkx_ci"',
        'CREATE DATABASE "drinkx_ci"',
    ]
    assert not any("not_disposable" in stmt for stmt in recorder.statements)


def test_the_probe_may_not_be_the_main_database_under_another_spelling():
    """Written without its default port it is still the same database."""
    with pytest.raises(UnsafeTestResource):
        plan_probe_database(
            "postgresql+asyncpg://ci:dummy@localhost/drinkx_test", "drinkx_test", purpose="test"
        )


def test_an_unusable_main_dsn_stops_planning_before_the_probe_is_considered():
    with pytest.raises(UnsafeDatabaseTarget):
        plan_probe_database(
            "postgresql+asyncpg://ci:dummy@77.105.168.227:5432/drinkx_crm",
            "drinkx_ci",
            purpose="test",
        )


def test_the_identifier_guard_does_not_rely_on_assert(tmp_path):
    """`python -O` strips assertions; this guard has to survive that."""
    import subprocess
    import sys

    script = tmp_path / "check.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_API_ROOT)!r})\n"
        "from scripts.db_test_resources import validate_database_identifier, UnsafeTestResource\n"
        "try:\n"
        "    validate_database_identifier('bad name', purpose='t')\n"
        "except UnsafeTestResource:\n"
        "    print('REFUSED')\n"
        "else:\n"
        "    print('ACCEPTED')\n"
    )
    out = subprocess.run(
        [sys.executable, "-O", str(script)], capture_output=True, text=True, timeout=60
    )
    assert out.stdout.strip() == "REFUSED", out.stderr[-500:]


def test_a_valid_identifier_is_returned_unchanged():
    assert validate_database_identifier("drinkx_ci", purpose="test") == "drinkx_ci"


# ---------------------------------------------------------------------------
# F2 — the lock identifies the database, not the string
# ---------------------------------------------------------------------------

EQUIVALENT = [
    "postgresql+asyncpg://ci:dummy@localhost/drinkx_test",
    "postgresql+asyncpg://ci:dummy@localhost:5432/drinkx_test",
    "postgresql+asyncpg://ci:other_password@localhost:5432/drinkx_test",
    "postgresql+asyncpg://other_user:dummy@LOCALHOST:5432/drinkx_test",
]


def test_every_spelling_of_one_database_gets_one_key():
    keys = {advisory_key(resolved_target(u)[2], purpose="p") for u in EQUIVALENT}
    assert len(keys) == 1, f"one database produced {len(keys)} different lock keys"


def test_two_names_for_one_host_get_one_key():
    """IMPLEMENTER (P2-1): `localhost` and `127.0.0.1` are one server."""
    aliases = [
        "postgresql+asyncpg://ci:dummy@localhost:5432/drinkx_test",
        "postgresql+asyncpg://ci:dummy@127.0.0.1:5432/drinkx_test",
    ]
    keys = {advisory_key(resolved_target(u)[2], purpose="p") for u in aliases}
    assert len(keys) == 1, "two names for one host produced two lock keys"


def test_the_resolved_target_matches_what_the_driver_would_use():
    """The normalisation is only safe if it agrees with the driver."""
    dialect = PGDialect_asyncpg()
    for url in EQUIVALENT:
        _, kwargs = dialect.create_connect_args(make_url(url))
        driver = (
            (kwargs.get("host") or "localhost").lower(),
            int(kwargs.get("port") or 5432),
            kwargs.get("database"),
        )
        assert resolved_target(url) == driver, url


def test_the_address_does_not_enter_the_key():
    """The key is the purpose and the database, nothing else (P2-1).

    A lock lives in one space per server, and the connection already fixes the
    server, so no spelling of the address may change the key.
    """
    base = advisory_key("drinkx_test", purpose="p")
    for url in (
        "postgresql+asyncpg://ci:dummy@localhost/drinkx_test",
        "postgresql+asyncpg://ci:dummy@127.0.0.1:5432/drinkx_test",
        "postgresql+asyncpg://ci:dummy@LOCALHOST:5432/drinkx_test",
    ):
        assert advisory_key(resolved_target(url)[2], purpose="p") == base, url


def test_the_suite_schema_lock_is_keyed_on_the_resolved_target():
    """The other half of F2: the lock the whole suite takes on its own database.

    Pinned to the derivation, not to a literal number, so the test survives a
    change of purpose string but not a return to hashing the DSN.
    """
    conftest = pytest.importorskip("tests.conftest")
    key = getattr(conftest, "_SCHEMA_LOCK_KEY", None)
    if key is None:
        pytest.skip("the schema lock only exists when PostgreSQL is configured")
    expected = advisory_key(
        resolved_target(conftest.TEST_DB_URL)[2], purpose="drinkx:test-schema"
    )
    assert key == expected, (
        "the schema lock key is not derived from the resolved database name, "
        "so the same database written another way would get a different key"
    )


def test_different_databases_and_purposes_get_different_keys():
    a = advisory_key("drinkx_test", purpose="p")
    b = advisory_key("drinkx_ci", purpose="p")
    c = advisory_key("drinkx_test", purpose="other")
    assert len({a, b, c}) == 3


def test_the_key_stays_inside_the_signed_64_bit_range():
    key = advisory_key("drinkx_test", purpose="p")
    assert 0 <= key < 2**63


def test_two_suites_sharing_one_probe_database_share_its_lock():
    """Different main databases, same probe: they must still serialise."""
    a = plan_probe_database(
        "postgresql+asyncpg://ci:dummy@localhost:5432/drinkx_test", "drinkx_ci", purpose="p"
    )
    b = plan_probe_database(
        "postgresql+asyncpg://ci:dummy@localhost/drinkx_migrations_test", "drinkx_ci", purpose="p"
    )
    assert a.lock_key == b.lock_key
    assert a.database == b.database == "drinkx_ci"


# ---------------------------------------------------------------------------
# F2 — the lock connection is released on every path
# ---------------------------------------------------------------------------


class FailingRecorder(Recorder):
    def __init__(self, fail_on: str):
        super().__init__()
        self.fail_on = fail_on

    async def connect(self, dsn, **kw):
        if self.fail_on == "connect":
            raise RuntimeError("connect failed")
        return await super().connect(dsn, **kw)


def test_a_failure_while_acquiring_leaves_nothing_running():
    lock = HeldAdvisoryLock("postgresql://ci@localhost/postgres", 1, connect=FailingRecorder("connect").connect)
    with pytest.raises(RuntimeError):
        lock.acquire()
    assert lock._loop is None and lock._thread is None and lock._conn is None


def test_release_is_idempotent():
    recorder = Recorder()
    lock = HeldAdvisoryLock("postgresql://ci@localhost/postgres", 1, connect=recorder.connect)
    assert lock.acquire() is True
    lock.release()
    lock.release()
    assert lock._loop is None and lock._conn is None


def test_a_refused_lock_closes_its_connection():
    class Busy(Recorder):
        async def connect(self, dsn, **_kw):
            self.connects.append(dsn)
            outer = self

            class Conn:
                async def fetchval(self, sql, *_a):
                    outer.statements.append(sql)
                    return False  # somebody else holds it

                async def close(self):
                    outer.statements.append("closed")

            return Conn()

    busy = Busy()
    lock = HeldAdvisoryLock("postgresql://ci@localhost/postgres", 1, connect=busy.connect)
    assert lock.acquire() is False
    assert "closed" in busy.statements
    assert lock._loop is None and lock._conn is None


def test_the_context_manager_reports_a_busy_resource_clearly():
    class Busy(Recorder):
        async def connect(self, dsn, **_kw):
            class Conn:
                async def fetchval(self, *_a):
                    return False

                async def close(self):
                    return None

            return Conn()

    with pytest.raises(UnsafeTestResource):
        with HeldAdvisoryLock("postgresql://ci:secret@localhost/postgres", 1, connect=Busy().connect):
            pass


def test_a_busy_lock_message_does_not_leak_the_password():
    class Busy(Recorder):
        async def connect(self, dsn, **_kw):
            class Conn:
                async def fetchval(self, *_a):
                    return False

                async def close(self):
                    return None

            return Conn()

    with pytest.raises(UnsafeTestResource) as excinfo:
        with HeldAdvisoryLock("postgresql://ci:hunter2@localhost/postgres", 1, connect=Busy().connect):
            pass
    assert "hunter2" not in str(excinfo.value)
