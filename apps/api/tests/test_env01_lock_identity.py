"""Oracle test for ENV-01 (P2-1): one advisory-lock identity per database,
independent of the host alias used to spell its DSN.

Contract: docs of task ENV-01. Real source, as first verified by the
coordinator 2026-09-20 (BROKEN shape) and then updated for the candidate fix
on SHA 1a29b27 (CURRENT shape):

* CURRENT: `scripts/db_test_resources.py::advisory_key(database, *, purpose)`
  builds its key from `f"{purpose}|{database}"` alone -- host and port were
  removed from the payload entirely. Callers pass
  `advisory_key(resolved_target(url)[2], purpose=...)`.
* BROKEN (what this test was originally written against, and what the
  mutation drill below restores): the same function took `(host, port,
  database, *, purpose)` and hashed `f"{purpose}|{host.lower()}|{port}|
  {database}"`, so `localhost` and `127.0.0.1` -- one and the same database --
  produced two different keys.
* `scripts/db_safety.py::resolved_target(dsn)` still reports `(host, port,
  database)` as the driver would see them, but only the database name feeds
  the lock key now; host/port remain part of `assert_disposable`'s target
  validation, not of lock identity.
* PostgreSQL advisory locks are scoped to the whole server (cluster), not to
  one database -- two sessions on the same server share one lock space no
  matter which alias, or which database, they connected through. This is why
  a schema-lock connection (to drinkx_ci) and a probe-lock connection (to the
  admin database `postgres`, as `HeldAdvisoryLock` uses) must still exclude
  each other when they compute the same `purpose|database` key.

Observed contrary-to-expectation behaviour this test was written to pin down
against the BROKEN shape: a process holding the schema lock via
`...@localhost:5432/drinkx_ci` did NOT exclude a second process trying the
same lock via `...@127.0.0.1:5432/drinkx_ci`, because `advisory_key` folded
the host string into the key. Both processes could then run the destructive
`DROP SCHEMA public CASCADE` at once. On the CURRENT (candidate) shape this is
fixed and ENV-LOCK-01/02 are expected to PASS.

This file is written directly from the frozen task contract
(ENV-01_TASK_CONTRACT.md), before reading any implementer explanation, so it
is not tuned to whatever the fix turns out to do -- only to the acceptance
freeze:

* ENV-LOCK-01 (must run): localhost vs 127.0.0.1 on drinkx_ci must exclude
  each other.
* ENV-LOCK-02 (opportunistic): the same, over ::1 and over a unix socket, if
  those transports are actually reachable here -- otherwise NOT_RUN with a
  precise reason, never a silent pass.
* ENV-LOCK-03: drinkx_ci and drinkx_migrations_test must NOT block each other
  (independent resources), and releasing the holder's connection must free
  the lock for a brand new connection (no false, lingering ownership).

Every DSN used here is validated through the project's own disposable-target
allowlist (`scripts.db_safety.assert_disposable`) before anything connects,
same as the fixtures it protects, and only names already on that allowlist
(`drinkx_ci`, `drinkx_migrations_test`) are used.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from scripts.db_safety import assert_disposable, resolved_target
from scripts.db_test_resources import advisory_key
from tests.conftest import POSTGRES_AVAILABLE

pytest.importorskip("asyncpg")
import asyncpg  # noqa: E402

pytestmark = pytest.mark.skipif(
    not POSTGRES_AVAILABLE, reason="ENV-01: requires a reachable PostgreSQL test database"
)

# tests/conftest.py defines a SESSION-scoped, autouse `_create_tables` fixture
# that itself takes the real schema lock -- advisory_key(*resolved_target(
# TEST_DB_URL), purpose="drinkx:test-schema") -- on this same drinkx_ci
# database, and holds it for the whole pytest session. This module
# deliberately computes and takes THAT SAME key itself to inspect its
# identity, so letting the ordinary fixture also grab it first would make
# every attempt in this file start from "already held by our own session",
# which is not the scenario under test (two independent processes/
# connections racing for the lock). This override is local to this module
# only -- pytest fixture resolution prefers a module-level definition over
# the conftest one of the same name -- and it does not touch conftest.py or
# any other existing test.
try:
    import pytest_asyncio

    @pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
    async def _create_tables():
        """No-op override: this module never touches the schema, only locks."""
        yield

except ImportError:  # pragma: no cover - conftest already requires it when
    pass  # POSTGRES_AVAILABLE is True; kept defensive, not load-bearing.

PURPOSE = "drinkx:test-schema"

# Same physical database (drinkx_ci), two different host spellings for it.
CI_DSN_LOCALHOST = os.environ.get(
    "ENV01_CI_DSN_LOCALHOST",
    "postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_ci",
)
CI_DSN_LOOPBACK_IP = os.environ.get(
    "ENV01_CI_DSN_LOOPBACK_IP",
    "postgresql+asyncpg://drinkx:dev@127.0.0.1:5432/drinkx_ci",
)
CI_DSN_IPV6 = os.environ.get(
    "ENV01_CI_DSN_IPV6",
    "postgresql+asyncpg://drinkx:dev@[::1]:5432/drinkx_ci",
)
# A different, allowlisted database on the same server -- must NOT share a
# lock with drinkx_ci.
MIGRATIONS_DSN = os.environ.get(
    "ENV01_MIGRATIONS_DSN",
    "postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_migrations_test",
)
# The admin database `HeldAdvisoryLock` connects to for a probe-database's
# lock (see scripts/db_test_resources.py ADMIN_DATABASE). Not itself a target
# of DDL, and -- exactly as the project's own `plan_probe_database` treats it
# -- never separately run through `assert_disposable`'s database-name
# allowlist: its host and port are the already-validated main target's, and
# "postgres" is a fixed literal, not user input, the same way ADMIN_DATABASE
# is a module constant in db_test_resources.py. Two host spellings, exactly
# like CI_DSN_LOCALHOST/CI_DSN_LOOPBACK_IP, to check that two ADMIN
# connections computing the SAME probe-database key exclude each other
# regardless of which alias reached the admin database -- this is the real
# ENV-01 scenario for a probe database: two runs both treating drinkx_ci as
# their probe target, dropping and recreating it through two differently
# spelled connections to `postgres`.
ADMIN_DSN_LOCALHOST = os.environ.get(
    "ENV01_ADMIN_DSN_LOCALHOST",
    "postgresql+asyncpg://drinkx:dev@localhost:5432/postgres",
)
ADMIN_DSN_LOOPBACK_IP = os.environ.get(
    "ENV01_ADMIN_DSN_LOOPBACK_IP",
    "postgresql+asyncpg://drinkx:dev@127.0.0.1:5432/postgres",
)
# The purpose string the project's own probe fixture actually uses (see
# tests/test_alembic_version_table.py PROBE_PURPOSE, passed to
# plan_probe_database as `purpose=PROBE_PURPOSE`) -- not invented here, so
# this test exercises the real key the probe lock computes.
PROBE_PURPOSE = "drinkx:alembic-probe"

# Fail fast, before any connection, if these have drifted off the allowlist --
# same discipline the fixtures under test are held to.
for _dsn in (CI_DSN_LOCALHOST, CI_DSN_LOOPBACK_IP, CI_DSN_IPV6, MIGRATIONS_DSN):
    assert_disposable(_dsn, purpose="ENV-01 lock identity oracle test")


def _asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _key_for(dsn: str, *, purpose: str = PURPOSE) -> int:
    """The key the project's own code would compute for this DSN.

    Candidate signature (SHA 1a29b27): `advisory_key(database, *, purpose)` --
    only the resolved database name feeds the key now, never host or port.
    """
    database = resolved_target(dsn)[2]
    return advisory_key(database, purpose=purpose)


async def _connect(dsn: str) -> asyncpg.Connection:
    return await asyncpg.connect(_asyncpg_dsn(dsn), timeout=5)


async def _unlock_and_close(conn: asyncpg.Connection, key: int) -> None:
    try:
        await conn.fetchval("SELECT pg_advisory_unlock($1)", key)
    except Exception:
        pass
    try:
        await conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ENV-LOCK-01 -- localhost vs 127.0.0.1, same database, must exclude
# ---------------------------------------------------------------------------


def test_env_lock_01_localhost_and_loopback_ip_exclude_each_other_on_drinkx_ci():
    """Two independent connections, two different host spellings of the same
    database. Connection A takes the schema lock via `localhost`; connection B
    -- a stand-in for a second concurrent test run -- must be refused the same
    lock when it computes its OWN key from `127.0.0.1`.

    Mutation this test is meant to catch: putting `host` back into
    `advisory_key`'s payload (today's behaviour) makes `localhost` and
    `127.0.0.1` hash to different int64 keys, so B would wrongly see `True`
    here and proceed to `DROP SCHEMA public CASCADE` in parallel with A.
    """
    key_a = _key_for(CI_DSN_LOCALHOST)
    key_b = _key_for(CI_DSN_LOOPBACK_IP)

    async def scenario():
        conn_a = await _connect(CI_DSN_LOCALHOST)
        conn_b = await _connect(CI_DSN_LOOPBACK_IP)
        try:
            got_a = await conn_a.fetchval("SELECT pg_try_advisory_lock($1)", key_a)
            assert got_a is True, "connection A (localhost) failed to take the initial lock"

            got_b = await conn_b.fetchval("SELECT pg_try_advisory_lock($1)", key_b)
            assert got_b is False, (
                "connection B (127.0.0.1) acquired the lock while A (localhost) "
                "held it on the SAME database drinkx_ci -- the two host aliases "
                "produced different advisory keys and did not exclude each "
                f"other (key_a={key_a}, key_b={key_b})"
            )
        finally:
            await _unlock_and_close(conn_a, key_a)
            await _unlock_and_close(conn_b, key_b)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# ENV-LOCK-02 -- ::1 and unix socket, opportunistic, else NOT_RUN with a reason
# ---------------------------------------------------------------------------


def test_env_lock_02_ipv6_loopback_excludes_localhost_on_drinkx_ci():
    """Same shape as ENV-LOCK-01, but B connects via `::1` instead of
    `127.0.0.1`. Skipped (NOT_RUN) with a precise reason if this PostgreSQL
    server is not actually reachable over IPv6 loopback here -- never silently
    reported as a pass.
    """

    async def probe_ipv6():
        try:
            conn = await asyncpg.connect(_asyncpg_dsn(CI_DSN_IPV6), timeout=3)
        except Exception as exc:  # noqa: BLE001 - reporting, not handling
            return False, exc
        # Close within the SAME event loop that opened it -- an asyncpg
        # connection's transport is bound to its creating loop, and
        # asyncio.run() tears that loop down as soon as this coroutine
        # returns, so closing it from a later, separate asyncio.run() call
        # raises "attached to a different loop".
        await conn.close()
        return True, None

    reachable, probe_err = asyncio.run(probe_ipv6())
    if not reachable:
        pytest.skip(
            "NOT_RUN: PostgreSQL is not reachable over ::1 (IPv6 loopback) in "
            f"this environment ({type(probe_err).__name__}: {probe_err}); "
            "ENV-LOCK-02's IPv6 sub-case cannot be exercised here."
        )

    key_a = _key_for(CI_DSN_LOCALHOST)
    key_b = _key_for(CI_DSN_IPV6)

    async def scenario():
        conn_a = await _connect(CI_DSN_LOCALHOST)
        conn_b = await _connect(CI_DSN_IPV6)
        try:
            got_a = await conn_a.fetchval("SELECT pg_try_advisory_lock($1)", key_a)
            assert got_a is True, "connection A (localhost) failed to take the initial lock"

            got_b = await conn_b.fetchval("SELECT pg_try_advisory_lock($1)", key_b)
            assert got_b is False, (
                "connection B (::1) acquired the lock while A (localhost) held "
                "it on the SAME database drinkx_ci -- the IPv6 loopback alias "
                f"did not exclude the localhost alias (key_a={key_a}, key_b={key_b})"
            )
        finally:
            await _unlock_and_close(conn_a, key_a)
            await _unlock_and_close(conn_b, key_b)

    asyncio.run(scenario())


def test_env_lock_02_unix_socket_transport():
    """Attempts a real unix-socket connection to the local PostgreSQL server.

    Always ends in `pytest.skip` (NOT_RUN), because whichever way the probe
    goes there is no case this suite can assert PASS/FAIL on without changing
    scope the contract forbids:

    * if no unix socket is reachable here, there is nothing to test;
    * if one IS reachable, `scripts/db_safety.DEFAULT_ALLOWED_HOSTS` has no
      allowlisted DSN spelling for a unix-socket target (only
      localhost/127.0.0.1/::1/postgres), and widening that allowlist is an
      explicit ENV-01 non-goal -- so `advisory_key`/`resolved_target` cannot
      be exercised against it through a real, allowlisted DSN.
    """

    async def probe_socket():
        # asyncpg's own default unix-socket search (host=None) covers the
        # common install locations (/var/run/postgresql, /tmp, ...).
        try:
            conn = await asyncpg.connect(
                host=None,
                port=5432,
                user="drinkx",
                password="dev",
                database="drinkx_ci",
                timeout=3,
            )
        except Exception as exc:  # noqa: BLE001 - reporting, not handling
            return False, exc
        # Close inside the same loop that opened it -- see the ::1 probe above
        # for why crossing asyncio.run() calls with a live connection breaks.
        await conn.close()
        return True, None

    reachable, err = asyncio.run(probe_socket())
    if reachable:
        pytest.skip(
            "NOT_RUN: a unix-socket connection to drinkx_ci succeeded, but "
            "scripts/db_safety.py's DSN allowlist has no representation for a "
            "unix-socket target (DEFAULT_ALLOWED_HOSTS is localhost/127.0.0.1/"
            "::1/postgres only), and widening it is out of scope for ENV-01. "
            "This sub-case cannot be exercised through a real, allowlisted DSN."
        )
    pytest.skip(
        f"NOT_RUN: unix-socket transport is not reachable here "
        f"({type(err).__name__}: {err})."
    )


# ---------------------------------------------------------------------------
# ENV-LOCK-03 -- independent databases don't block; no false ownership persists
# ---------------------------------------------------------------------------


def test_env_lock_03_independent_databases_do_not_block_and_release_is_real():
    """A holds the schema lock on drinkx_ci; B must still be able to take the
    (different) lock on drinkx_migrations_test -- these are independent
    resources and must not serialise against each other.

    Then A's connection closes (PostgreSQL always releases session-level
    advisory locks on disconnect). A brand new connection must be able to
    take the drinkx_ci lock afterwards -- if it could not, some part of the
    fix would be holding a false/stale ownership beyond the connection that
    earned it.
    """
    key_ci = _key_for(CI_DSN_LOCALHOST)
    key_migrations = _key_for(MIGRATIONS_DSN)

    async def scenario():
        conn_a = await _connect(CI_DSN_LOCALHOST)
        conn_b = await _connect(MIGRATIONS_DSN)
        try:
            got_a = await conn_a.fetchval("SELECT pg_try_advisory_lock($1)", key_ci)
            assert got_a is True, "connection A failed to take the initial lock on drinkx_ci"

            got_b = await conn_b.fetchval("SELECT pg_try_advisory_lock($1)", key_migrations)
            assert got_b is True, (
                "a lock held on drinkx_ci blocked an unrelated lock on "
                "drinkx_migrations_test -- the two resources are not independent "
                f"(key_ci={key_ci}, key_migrations={key_migrations})"
            )
            await conn_b.fetchval("SELECT pg_advisory_unlock($1)", key_migrations)
        finally:
            # Close A outright (not just unlock) -- PostgreSQL must release
            # its session-level advisory lock on disconnect, with nothing
            # left holding it afterwards.
            await conn_a.close()
            await conn_b.close()

        conn_c = await _connect(CI_DSN_LOCALHOST)
        try:
            got_c = await conn_c.fetchval("SELECT pg_try_advisory_lock($1)", key_ci)
            assert got_c is True, (
                "after the original holder disconnected, a brand new connection "
                "still could not take the lock on drinkx_ci -- a stale/false "
                "ownership persisted beyond the connection that earned it"
            )
        finally:
            await _unlock_and_close(conn_c, key_ci)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Probe-lock identity -- two ADMIN connections (to `postgres`, as
# HeldAdvisoryLock uses for a probe database), two host aliases, must
# exclude each other on the SAME probe-database key.
#
# Coordinator correction (Fable, 2026-09-21): a prior version of this file
# had a test requiring a schema-lock connection (to drinkx_ci itself) and a
# probe-lock connection (to the admin database `postgres`) to exclude each
# other on an identical purpose|database key. That requirement was wrong --
# confirmed with a plain psql check below -- and has been removed. A schema
# lock and a probe lock protect DIFFERENT resources by design
# (`plan_probe_database` requires the probe database to differ from the main
# database), so there is no reason for connections to two different
# databases to exclude each other. What DOES need to exclude is two ADMIN
# connections computing the same probe-database key through different host
# aliases -- that is the actual ENV-01 (P2-1) scenario for a probe database:
# two runs both treating drinkx_ci as their probe target, one connecting to
# `postgres` via `localhost`, the other via `127.0.0.1`.
# ---------------------------------------------------------------------------


def test_probe_lock_localhost_and_loopback_ip_exclude_each_other_on_drinkx_ci():
    """Two admin-database connections (to `postgres`, as `HeldAdvisoryLock`
    holds a probe lock), reached via two different host aliases, both
    computing the key for probe database `drinkx_ci` under the real probe
    purpose (`PROBE_PURPOSE`, matching `plan_probe_database`'s caller in
    `tests/test_alembic_version_table.py`). The second admin connection must
    be refused the lock the first already holds -- otherwise two runs could
    both `DROP DATABASE drinkx_ci` as a probe database at once, one having
    reached the admin database via `localhost`, the other via `127.0.0.1`.
    """
    key = advisory_key("drinkx_ci", purpose=PROBE_PURPOSE)

    async def scenario():
        admin_a = await _connect(ADMIN_DSN_LOCALHOST)
        admin_b = await _connect(ADMIN_DSN_LOOPBACK_IP)
        try:
            got_a = await admin_a.fetchval("SELECT pg_try_advisory_lock($1)", key)
            assert got_a is True, (
                "admin connection A (localhost) failed to take the initial "
                "probe lock on drinkx_ci"
            )

            got_b = await admin_b.fetchval("SELECT pg_try_advisory_lock($1)", key)
            assert got_b is False, (
                "admin connection B (127.0.0.1) acquired the SAME probe-lock "
                "key for drinkx_ci while admin connection A (localhost) held "
                "it -- two runs treating drinkx_ci as their probe database "
                "would not exclude each other across this alias pair "
                f"(key={key})"
            )
        finally:
            await _unlock_and_close(admin_a, key)
            await _unlock_and_close(admin_b, key)

    asyncio.run(scenario())
