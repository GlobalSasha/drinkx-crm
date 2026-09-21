"""The DSN guard must agree with the driver about where a connection goes.

Review finding R1: the guard read only `urlsplit(...).hostname/.port/.path`, so a
URL query could redirect the driver somewhere else entirely while the guard saw
an allowlisted target:

    postgresql+asyncpg://ci:dummy@localhost:5432/drinkx_test
        ?host=elsewhere.invalid&database=not_disposable

The guard said "allowed"; SQLAlchemy's asyncpg dialect resolved that to
host=elsewhere.invalid, database=not_disposable. The fixtures behind this guard
run DROP SCHEMA public CASCADE, so a disagreement of that kind is not a
theoretical problem.

Every case here uses fictional values, and nothing in this file opens a
connection to anything.
"""
from __future__ import annotations

import pytest
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.engine import make_url

from scripts.db_safety import (
    DEFAULT_ALLOWED_DATABASES,
    DEFAULT_ALLOWED_HOSTS,
    UnsafeDatabaseTarget,
    assert_disposable,
    redact,
)

GOOD = "postgresql+asyncpg://ci:dummy@localhost:5432/drinkx_test"

# Fictional. Never used to connect — the guard must reject them before anything
# would try, which is the point of every assertion below.
REDIRECTING = [
    pytest.param(
        f"{GOOD}?host=elsewhere.invalid&database=not_disposable",
        id="host-and-database-override",
    ),
    pytest.param(f"{GOOD}?database=not_disposable", id="database-override"),
    pytest.param(f"{GOOD}?port=6543", id="port-override"),
    pytest.param(f"{GOOD}?host=first.invalid&host=second.invalid", id="repeated-host"),
    pytest.param(f"{GOOD}?%68ost=encoded.invalid", id="percent-encoded-key"),
    pytest.param(f"{GOOD}?HOST=upper.invalid", id="upper-case-key"),
    pytest.param(f"{GOOD}?options=-c%20search_path%3Devil", id="options-parameter"),
    pytest.param(f"{GOOD}#fragment", id="fragment"),
    pytest.param(f"{GOOD}?", id="empty-query-marker"),
]


@pytest.mark.parametrize("dsn", REDIRECTING)
def test_a_query_that_could_move_the_target_is_refused(dsn):
    with pytest.raises(UnsafeDatabaseTarget):
        assert_disposable(dsn, purpose="test")


def test_a_plain_allowlisted_dsn_is_still_accepted():
    assert_disposable(GOOD, purpose="test")


@pytest.mark.parametrize(
    "dsn",
    [
        pytest.param(GOOD, id="baseline"),
        pytest.param(
            "postgresql+asyncpg://ci:dummy@127.0.0.1:5432/drinkx_migrations_test",
            id="migration-database",
        ),
        pytest.param("postgresql+asyncpg://ci@localhost/drinkx_ci", id="default-port"),
    ],
)
def test_whatever_the_guard_accepts_is_where_the_driver_would_actually_go(dsn):
    """The invariant behind R1, checked against the real dialect.

    Reading the URL ourselves and hoping it matches the driver is what failed.
    Ask SQLAlchemy what it would connect to and require that to be allowlisted.
    `create_connect_args` only computes arguments; it opens nothing.
    """
    assert_disposable(dsn, purpose="test")

    _, kwargs = PGDialect_asyncpg().create_connect_args(make_url(dsn))
    host = kwargs.get("host") or "localhost"
    port = kwargs.get("port") or 5432
    database = kwargs.get("database")

    assert host in DEFAULT_ALLOWED_HOSTS, f"driver would reach host {host!r}"
    assert int(port) == 5432, f"driver would reach port {port!r}"
    assert database in DEFAULT_ALLOWED_DATABASES, f"driver would reach database {database!r}"


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+asyncpg://ci:hunter2@localhost:5432/drinkx_test",
        "postgresql+asyncpg://ci@localhost:5432/drinkx_test?password=hunter2",
        "postgresql+asyncpg://ci:hunter2@evil.invalid:5432/prod?password=hunter2",
    ],
)
def test_redact_never_returns_a_password(dsn):
    assert "hunter2" not in redact(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+asyncpg://ci:hunter2@evil.invalid:5432/drinkx_test",
        "postgresql+asyncpg://ci@localhost:5432/drinkx_test?password=hunter2",
        "postgresql+asyncpg://ci:hunter2@localhost:5432/production_db",
        "mysql://ci:hunter2@localhost/drinkx_test",
    ],
)
def test_a_refusal_never_quotes_a_password(dsn):
    with pytest.raises(UnsafeDatabaseTarget) as excinfo:
        assert_disposable(dsn, purpose="test")
    assert "hunter2" not in str(excinfo.value)


def test_the_guard_refuses_without_opening_a_connection(monkeypatch):
    """A refusal must happen before any driver call, not after one."""
    import asyncpg

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("the guard tried to connect before deciding")

    monkeypatch.setattr(asyncpg, "connect", explode)
    with pytest.raises(UnsafeDatabaseTarget):
        assert_disposable(
            "postgresql+asyncpg://ci:dummy@77.105.168.227:5432/drinkx_crm",
            purpose="test",
        )


@pytest.mark.parametrize(
    "dsn",
    [
        pytest.param("", id="empty"),
        pytest.param("postgresql+asyncpg://ci@evil.invalid:5432/drinkx_test", id="host"),
        pytest.param("postgresql+asyncpg://ci@localhost:5432/drinkx_crm", id="database"),
        pytest.param(
            "postgresql+asyncpg://ci@localhost:5432/prod_latest_test_backup",
            id="name-merely-containing-test",
        ),
        pytest.param("mysql://ci@localhost/drinkx_test", id="scheme"),
        pytest.param("postgresql+asyncpg://ci@localhost:6543/drinkx_test", id="port"),
    ],
)
def test_existing_allowlist_rules_still_hold(dsn):
    with pytest.raises(UnsafeDatabaseTarget):
        assert_disposable(dsn, purpose="test")


def test_the_allowlist_stays_deliberately_configurable(monkeypatch):
    monkeypatch.setenv("TEST_DB_ALLOWED_NAMES", "some_other_disposable_db")
    assert_disposable(
        "postgresql+asyncpg://ci@localhost:5432/some_other_disposable_db",
        purpose="test",
    )
    with pytest.raises(UnsafeDatabaseTarget):
        assert_disposable(GOOD, purpose="test")
