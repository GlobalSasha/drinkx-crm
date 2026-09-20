"""Validated, coordinated access to the disposable databases the tests destroy.

Two review findings live here.

F1: the probe fixture used to compose `DROP DATABASE "<name>"` from an
environment variable and send it, and only afterwards ask whether that name
was allowed. With `ALEMBIC_PROBE_DB='evil"; DROP DATABASE drinkx_crm; --'` the
statement it built named the production database. So every target this fixture
will touch is now decided, validated and frozen before the first connection is
opened, and the database name is checked as an identifier rather than trusted
inside a quoted string.

F2 / P2-1: the advisory lock protecting a destroyed database was keyed on the
DSN string, so `…@localhost/drinkx_test` and `…@localhost:5432/drinkx_test` —
the same database — produced different keys and did not exclude each other.
Keying it on the resolved target fixed the port half and left the host half:
`localhost` and `127.0.0.1` are one server written two ways, and again gave
two keys. An advisory lock is scoped to the whole server, so the key now names
only the purpose and the database, and the address is left out of it entirely.
The probe database also gets a lock of its own, held for the whole fixture
lifetime from the admin database, because a connection inside a database
cannot guard that database's own DROP.

This is a helper for these test resources, not a general locking service.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from scripts.db_safety import (
    UnsafeDatabaseTarget,
    assert_disposable,
    redact,
    resolved_target,
)

# Connected to in order to create and drop another database; never itself a
# target of DDL. Its host and port come from the already-validated main DSN.
ADMIN_DATABASE = "postgres"

# PostgreSQL identifiers are limited to 63 bytes. The charset is deliberately
# narrower than PostgreSQL allows: a name that needs quoting has no business
# being a disposable test database, and refusing it removes the question of
# whether the quoting is right.
_SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

LOCK_ACQUIRE_TIMEOUT_S = 30


class UnsafeTestResource(UnsafeDatabaseTarget):
    """A test resource was not provably safe to create, lock or destroy."""


def validate_database_identifier(name: object, *, purpose: str) -> str:
    """Accept only a plain lower-case identifier, and raise otherwise.

    A real exception, not `assert`: assertions vanish under `python -O`, and a
    guard in front of DROP DATABASE must not be something an interpreter flag
    can switch off.
    """
    if not isinstance(name, str) or not _SAFE_IDENTIFIER.match(name):
        shown = name if isinstance(name, str) else type(name).__name__
        raise UnsafeTestResource(
            f"{purpose}: {shown!r} is not a plain database identifier. Expected "
            "lower-case letters, digits and underscores, starting with a letter "
            "or underscore, at most 63 characters."
        )
    return name


def advisory_key(database: str, *, purpose: str) -> int:
    """A stable PostgreSQL advisory-lock key for one database and one purpose.

    Derived from the database name alone — never from the DSN string, and no
    longer from the host or port. A PostgreSQL advisory lock lives in one lock
    space per server, so the server is already fixed by the connection the lock
    is taken on. Putting its address into the key adds nothing, while a second
    spelling of that address — `localhost` against `127.0.0.1`, a name against
    its IP — silently produced a second key for the same database, and two
    destructive runs stopped excluding each other (review finding P2-1).

    The database name keeps two disposable databases on one server apart; the
    purpose keeps unrelated locks on one database from colliding. Host and port
    are still checked by `assert_disposable` — they identify the target, they
    just do not identify the lock.
    """
    payload = f"{purpose}|{database}"
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big") % (2**63)


def asyncpg_dsn(url: str) -> str:
    """The SQLAlchemy URL as asyncpg wants it."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@dataclass(frozen=True)
class ProbePlan:
    """Everything the probe fixture is allowed to touch, decided up front."""

    database: str
    probe_url: str
    admin_url: str
    lock_key: int


def plan_probe_database(main_url: str, probe_name: object, *, purpose: str) -> ProbePlan:
    """Validate every target before anything connects, and freeze the result.

    Raises `UnsafeTestResource` (or `UnsafeDatabaseTarget`) without opening a
    connection or composing any statement if the main DSN, the probe name, the
    probe DSN or the separation from the main database is not acceptable.
    """
    # 1. The DSN the whole suite runs against must itself be disposable.
    assert_disposable(main_url, purpose=f"{purpose}: main database")

    # 2. The probe name, as an identifier, before it ever reaches SQL.
    database = validate_database_identifier(probe_name, purpose=f"{purpose}: probe database name")

    parts = urlsplit(main_url)

    # 3. The probe DSN, through the same allowlist as everything else.
    probe_url = urlunsplit((parts.scheme, parts.netloc, f"/{database}", "", ""))
    assert_disposable(probe_url, purpose=f"{purpose}: probe database")

    # 4. It must not be the database the rest of the suite drops schemas in.
    #    Compared on resolved targets, so a different spelling of the same
    #    database cannot slip past.
    main_target = resolved_target(main_url)
    probe_target = resolved_target(probe_url)
    if probe_target == main_target:
        raise UnsafeTestResource(
            f"{purpose}: the probe database resolves to the same target as the "
            f"main test database ({main_target[0]}:{main_target[1]}/{main_target[2]}). "
            "These fixtures drop and recreate it, so they must be different databases."
        )

    # 5. The administrative connection inherits the validated host and port.
    admin_url = urlunsplit((parts.scheme, parts.netloc, f"/{ADMIN_DATABASE}", "", ""))

    name = probe_target[2]
    return ProbePlan(
        database=name,
        probe_url=probe_url,
        admin_url=admin_url,
        lock_key=advisory_key(name, purpose=purpose),
    )


async def recreate_probe_database(plan: ProbePlan, *, connect=None) -> None:
    """Drop and recreate the planned probe database, nothing else.

    `plan.database` came through `validate_database_identifier`, so quoting it
    cannot change the statement's shape.
    """
    if connect is None:  # pragma: no cover - exercised against a real server
        import asyncpg

        connect = asyncpg.connect

    conn = await connect(asyncpg_dsn(plan.admin_url), timeout=10)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{plan.database}"')
        await conn.execute(f'CREATE DATABASE "{plan.database}"')
    finally:
        await conn.close()


class HeldAdvisoryLock:
    """An advisory lock held across several unrelated `asyncio.run` calls.

    The probe fixture must hold its lock from before the DROP until after the
    last statement of the test, while the test body runs its own event loops.
    A connection cannot span those, so this one lives on a loop of its own in
    a background thread. Held on the admin database: a connection inside the
    probe database would itself block the DROP it is supposed to guard.
    """

    def __init__(self, dsn: str, key: int, *, connect=None):
        self._dsn = dsn
        self._key = key
        self._connect = connect
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._conn = None

    def _submit(self, coro):
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(LOCK_ACQUIRE_TIMEOUT_S)

    def acquire(self) -> bool:
        """True if the lock was taken. On any failure nothing is left open."""
        connect = self._connect
        if connect is None:  # pragma: no cover - exercised against a real server
            import asyncpg

            connect = asyncpg.connect

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="probe-db-lock", daemon=True
        )
        self._thread.start()
        try:
            self._conn = self._submit(connect(self._dsn, timeout=10))
            taken = bool(self._submit(self._conn.fetchval("SELECT pg_try_advisory_lock($1)", self._key)))
        except BaseException:
            self.release()
            raise
        if not taken:
            self.release()
        return taken

    def release(self) -> None:
        """Idempotent. Safe to call when acquire failed part way through."""
        try:
            if self._conn is not None:
                try:
                    self._submit(self._conn.fetchval("SELECT pg_advisory_unlock($1)", self._key))
                except Exception:
                    # Losing the connection already released the lock.
                    pass
                try:
                    self._submit(self._conn.close())
                except Exception:
                    pass
                self._conn = None
        finally:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread is not None:
                    self._thread.join(timeout=5)
                self._loop.close()
                self._loop = None
                self._thread = None

    def __enter__(self) -> "HeldAdvisoryLock":
        if not self.acquire():
            raise UnsafeTestResource(
                f"another run already holds the lock on {redact(self._dsn)} "
                f"(key {self._key}). These fixtures drop and recreate a database, "
                "so they must not overlap."
            )
        return self

    def __exit__(self, *_exc) -> None:
        self.release()
