"""Refuse to touch anything but a disposable database.

The test fixtures run `DROP SCHEMA public CASCADE`, and the migration check
runs a real `alembic upgrade head`. Both are unrecoverable against the wrong
target, and both take their DSN from the environment, where a stray
`DATABASE_URL` or a copy-pasted production string is one mistake away.

The guard below is deliberately an allowlist over the parsed URL — scheme,
host, port and database name each checked on their own. Substring matching on
"test" is not a safety property: `prod_latest_backup` contains it.

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
    """The DSN with any password replaced, safe to print in logs and errors."""
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<unparseable dsn>"
    if parts.password is None:
        return dsn
    netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
    return parts._replace(netloc=netloc).geturl()


def assert_disposable(dsn: str, *, purpose: str) -> None:
    """Raise UnsafeDatabaseTarget unless `dsn` names a throwaway database.

    Called before opening a connection, so a wrong target never reaches the
    network, let alone a DDL statement.
    """
    safe = redact(dsn)

    if not dsn or not dsn.strip():
        raise UnsafeDatabaseTarget(f"{purpose}: no database URL configured")

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
