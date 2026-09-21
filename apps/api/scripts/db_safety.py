"""Refuse to touch anything but a disposable database.

The test fixtures run `DROP SCHEMA public CASCADE`, and the migration check
runs a real `alembic upgrade head`. Both are unrecoverable against the wrong
target, and both take their DSN from the environment, where a stray
`DATABASE_URL` or a copy-pasted production string is one mistake away.

The guard below is deliberately an allowlist over the parsed URL — scheme,
host, port and database name each checked on their own. Substring matching on
"test" is not a safety property: `prod_latest_backup` contains it.

It also refuses any URL carrying a query string or a fragment. Reading the URL
ourselves and trusting that the driver reads it the same way is exactly what
failed review finding R1:

    postgresql+asyncpg://ci:pw@localhost:5432/drinkx_test
        ?host=elsewhere.invalid&database=not_disposable

`urlsplit` reports an allowlisted host and database for that string, while
SQLAlchemy's asyncpg dialect resolves it to elsewhere.invalid/not_disposable.
Rather than re-implement every override rule the driver honours — repeated
keys, percent-encoded names, `options`, future parameters — the supported DSN
form is closed: authority and path only. A connection string that needs more
is a deliberate change here, not something that slips through.

Override for a different disposable setup with TEST_DB_ALLOWED_HOSTS,
TEST_DB_ALLOWED_PORTS and TEST_DB_ALLOWED_NAMES (comma-separated).
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset(
    {
        "postgresql",
        "postgresql+asyncpg",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }
)

DEFAULT_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres"})
DEFAULT_ALLOWED_PORTS = frozenset({5432})
DEFAULT_ALLOWED_DATABASES = frozenset(
    {"drinkx_test", "drinkx_ci", "drinkx_migrations_test"}
)


class UnsafeDatabaseTarget(RuntimeError):
    """The configured DSN is not a database we are allowed to destroy."""


def _from_env(name: str, default: frozenset[str]) -> frozenset[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def redact(dsn: str) -> str:
    """A description of the target that is safe to print in logs and errors.

    Rebuilt field by field rather than patched in place. A password can sit in
    the userinfo *and* in the query (`?password=...`), so masking one of them
    by string surgery leaves the other in the log. Anything not needed to
    identify the target — the query above all — is dropped rather than masked.
    """
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<unparseable dsn>"

    scheme = parts.scheme or "<no-scheme>"
    try:
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        host, port = "<invalid-host-or-port>", None

    user = parts.username
    if user and parts.password is not None:
        userinfo = f"{user}:***@"
    elif user:
        userinfo = f"{user}@"
    else:
        userinfo = ""

    authority = f"{userinfo}{host}" + (f":{port}" if port is not None else "")
    database = parts.path.lstrip("/")
    tail = " [query removed]" if ("?" in dsn or "#" in dsn) else ""
    return f"{scheme}://{authority}/{database}{tail}"


DEFAULT_PORT = 5432


def resolved_target(dsn: str) -> tuple[str, int, str]:
    """`(host, port, database)` as the driver will actually see them.

    One database can be written several ways — with the port left implicit,
    with different credentials, with the host as a name or as its IP — and
    those spellings must not look like different resources. Anything compared
    as a raw string gets that wrong: review finding F2 found two advisory lock
    keys for one database, so two runs failed to exclude each other.

    Used to compare and describe targets. Advisory lock keys are no longer
    derived from it — a lock lives in the lock space of the database its
    connection is attached to, which any spelling of the address reaches
    alike, so only the purpose and the database name enter the key (see
    `db_test_resources.advisory_key`).

    Only meaningful after `assert_disposable`: it is the closed DSN contract,
    with no query allowed, that makes this triple match what the driver
    resolves.
    """
    parts = urlsplit(dsn)
    try:
        port = parts.port
    except ValueError:
        port = None
    return (parts.hostname or "localhost").lower(), int(port or DEFAULT_PORT), parts.path.lstrip("/")


def assert_disposable(dsn: str, *, purpose: str) -> None:
    """Raise UnsafeDatabaseTarget unless `dsn` names a throwaway database.

    Called before opening a connection, so a wrong target never reaches the
    network, let alone a DDL statement.
    """
    safe = redact(dsn)

    if not dsn or not dsn.strip():
        raise UnsafeDatabaseTarget(f"{purpose}: no database URL configured")

    # Refuse query and fragment before parsing anything else. The driver, not
    # this function, decides what a query means, and it can move the host, the
    # port and the database out from under every check below (finding R1).
    # Detected on the raw string: `urlsplit` reports an empty query for a bare
    # trailing "?", which would otherwise slip past.
    if "?" in dsn or "#" in dsn:
        raise UnsafeDatabaseTarget(
            f"{purpose}: the URL carries a query string or fragment, which can "
            f"redirect the driver to a different host, port or database than "
            f"this guard sees. Supported form is scheme://user:password@host:port/database "
            f"with nothing after it. Target as parsed here: {safe}"
        )

    try:
        parts = urlsplit(dsn)
    except ValueError as exc:
        raise UnsafeDatabaseTarget(f"{purpose}: cannot parse {safe}: {exc}") from exc

    if parts.scheme not in ALLOWED_SCHEMES:
        raise UnsafeDatabaseTarget(
            f"{purpose}: scheme {parts.scheme!r} is not a PostgreSQL driver "
            f"this guard knows ({safe})"
        )

    try:
        host = parts.hostname
        port = parts.port
    except ValueError as exc:  # malformed port
        raise UnsafeDatabaseTarget(f"{purpose}: bad host/port in {safe}: {exc}") from exc

    # asyncpg accepts a comma-separated host list; only the allowlisted one
    # would be checked here while the driver may reach any of them.
    if host and "," in host:
        raise UnsafeDatabaseTarget(
            f"{purpose}: the URL names more than one host, which this guard "
            f"cannot check as a single target ({safe})"
        )

    allowed_hosts = _from_env("TEST_DB_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS)
    if not host or host not in allowed_hosts:
        raise UnsafeDatabaseTarget(
            f"{purpose}: host {host!r} is not a disposable test host "
            f"(allowed: {sorted(allowed_hosts)}) — refusing {safe}"
        )

    allowed_ports = {int(p) for p in _from_env("TEST_DB_ALLOWED_PORTS", frozenset(str(p) for p in DEFAULT_ALLOWED_PORTS))}
    effective_port = port if port is not None else 5432
    if effective_port not in allowed_ports:
        raise UnsafeDatabaseTarget(
            f"{purpose}: port {effective_port} is not allowed "
            f"(allowed: {sorted(allowed_ports)}) — refusing {safe}"
        )

    database = parts.path.lstrip("/")
    allowed_names = _from_env("TEST_DB_ALLOWED_NAMES", DEFAULT_ALLOWED_DATABASES)
    if database not in allowed_names:
        raise UnsafeDatabaseTarget(
            f"{purpose}: database {database!r} is not on the disposable allowlist "
            f"({sorted(allowed_names)}) — refusing {safe}. Containing the word "
            f"'test' is not enough; add it to TEST_DB_ALLOWED_NAMES deliberately."
        )
