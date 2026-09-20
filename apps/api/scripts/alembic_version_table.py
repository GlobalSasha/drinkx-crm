"""Keep Alembic's bookkeeping table wide enough — and touch it only when it is not.

Alembic hardcodes `Column("version_num", String(32))` for `alembic_version`
(alembic/ddl/impl.py, `version_table_impl`) and offers no option to widen it.
Seven revision ids in this project are longer than 32 characters, the first
being `0009_inbox_items_and_activity_email` at 35, so `upgrade head` against a
NEW database dies there with:

    StringDataRightTruncationError: value too long for type character varying(32)

A fresh environment — disaster recovery, a new staging box, a wiped volume —
could therefore not be built from the chain at all, because the API container
runs `alembic upgrade head` before uvicorn starts.

The first fix ran CREATE IF NOT EXISTS plus ALTER TYPE on every single
invocation. Review finding R3: that re-issues DDL against a table that is
already correct, it can *narrow* a column that someone widened further or made
unlimited, and `ALTER TABLE ... TYPE` takes an ACCESS EXCLUSIVE lock, so an
unrelated open transaction holding a read on the table can stall the deploy
with no bound on the wait.

So: look first, act only on a genuinely narrow column, and bound the wait for
that one statement.

This lives outside `alembic/env.py` so it can be tested without importing
`env.py`, which runs migrations as a side effect of being imported.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

VERSION_TABLE = "alembic_version"
VERSION_COLUMN = "version_num"

# Comfortably past the longest revision id in the chain (39 characters) with
# room for the naming style to grow.
TARGET_WIDTH = 255

# The widening is a single-row DDL statement. If it cannot take its lock in a
# few seconds, something else is holding the table and waiting forever inside
# a deploy is worse than failing with a clear message. This bounds ONLY the
# bootstrap statement: the migration chain that follows, including long index
# builds, keeps its own behaviour.
DEFAULT_LOCK_TIMEOUT_MS = 5000

# What the column looks like right now.
MISSING = "missing"      # no such table
LIMITED = "limited"      # character varying(N)
UNLIMITED = "unlimited"  # text, or a varchar with no declared length

# What was done about it.
CREATED = "created"
WIDENED = "widened"
UNCHANGED = "unchanged"


def inspect_version_column(connection: Connection) -> tuple[str, int | None]:
    """Return the current shape of `alembic_version.version_num`.

    ``(MISSING, None)``, ``(UNLIMITED, None)`` or ``(LIMITED, width)``.
    """
    row = connection.execute(
        text(
            """
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table
              AND column_name = :column
            """
        ),
        {"table": VERSION_TABLE, "column": VERSION_COLUMN},
    ).first()

    if row is None:
        return MISSING, None

    _data_type, max_length = row
    if max_length is None:
        # `text`, or a varchar declared without a length: already unbounded.
        return UNLIMITED, None
    return LIMITED, int(max_length)


def ensure_version_table_width(
    connection: Connection,
    *,
    target_width: int = TARGET_WIDTH,
    lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS,
) -> str:
    """Make sure the bookkeeping column can hold this project's revision ids.

    Returns ``CREATED``, ``WIDENED`` or ``UNCHANGED``. Emits no DDL in the
    ``UNCHANGED`` case, which is the normal one on every run after the first.

    The connection is left with no open transaction, whichever branch runs.
    Alembic's ``begin_transaction()`` treats an already-active transaction as
    somebody else's and hands back a no-op, which breaks the ``autocommit_block``
    that a couple of migrations use for ``CREATE INDEX CONCURRENTLY``.
    """
    state, width = inspect_version_column(connection)

    if state == MISSING:
        connection.exec_driver_sql(
            f"CREATE TABLE {VERSION_TABLE} ("
            f"{VERSION_COLUMN} VARCHAR({target_width}) NOT NULL, "
            f"CONSTRAINT {VERSION_TABLE}_pkc PRIMARY KEY ({VERSION_COLUMN}))"
        )
        connection.commit()
        return CREATED

    # Never narrow. An unlimited column already holds anything, and a wider one
    # was a deliberate choice by whoever made it.
    if state == UNLIMITED or (width is not None and width >= target_width):
        connection.rollback()
        return UNCHANGED

    # SET LOCAL scopes the timeout to this transaction, so the bound applies to
    # the ALTER and to nothing else.
    connection.exec_driver_sql(f"SET LOCAL lock_timeout = '{int(lock_timeout_ms)}ms'")
    connection.exec_driver_sql(
        f"ALTER TABLE {VERSION_TABLE} "
        f"ALTER COLUMN {VERSION_COLUMN} TYPE VARCHAR({target_width})"
    )
    connection.commit()
    return WIDENED
