"""Regression tests for the bounded Alembic autogenerate policy."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from scripts.alembic_drift_policy import (
    compare_server_default,
    compare_type,
    include_object,
)


def _column(table_name: str, column_name: str, type_: sa.types.TypeEngine) -> sa.Column:
    table = sa.Table(table_name, sa.MetaData(), sa.Column(column_name, type_))
    return table.c[column_name]


def test_known_reflected_db_only_index_is_migration_owned() -> None:
    table = sa.Table("activities", sa.MetaData(), sa.Column("archived_at", sa.DateTime))
    index = sa.Index("ix_activities_archived_at", table.c.archived_at)

    assert include_object(index, index.name, "index", True, None) is False


def test_unknown_db_only_index_is_not_suppressed() -> None:
    table = sa.Table("activities", sa.MetaData(), sa.Column("archived_at", sa.DateTime))
    index = sa.Index("ix_unexpected_new_index", table.c.archived_at)

    assert include_object(index, index.name, "index", True, None) is True


def test_metadata_only_and_paired_indexes_are_still_compared() -> None:
    table = sa.Table("activities", sa.MetaData(), sa.Column("archived_at", sa.DateTime))
    index = sa.Index("ix_activities_archived_at", table.c.archived_at)

    assert include_object(index, index.name, "index", False, None) is True
    assert include_object(index, index.name, "index", True, object()) is True


def test_known_db_only_server_default_is_preserved() -> None:
    column = _column("leads", "score", sa.Integer())
    inspected_default = sa.DefaultClause(sa.text("0"))

    assert (
        compare_server_default(
            None,
            None,
            column,
            inspected_default,
            None,
            None,
        )
        is False
    )


def test_unknown_db_only_server_default_is_not_suppressed() -> None:
    column = _column("leads", "future_column", sa.Integer())
    inspected_default = sa.DefaultClause(sa.text("0"))

    assert (
        compare_server_default(
            None,
            None,
            column,
            inspected_default,
            None,
            None,
        )
        is None
    )


def test_explicit_metadata_server_default_uses_normal_comparison() -> None:
    column = _column("leads", "score", sa.Integer())
    inspected_default = sa.DefaultClause(sa.text("0"))
    metadata_default = sa.DefaultClause(sa.text("1"))

    assert (
        compare_server_default(
            None,
            None,
            column,
            inspected_default,
            metadata_default,
            "1",
        )
        is None
    )


def test_known_jsonb_storage_with_json_orm_is_equivalent() -> None:
    column = _column("leads", "agent_state", sa.JSON())

    assert (
        compare_type(
            None,
            None,
            column,
            JSONB(),
            column.type,
        )
        is False
    )


def test_jsonb_json_mismatch_elsewhere_is_not_suppressed() -> None:
    column = _column("other_table", "payload", sa.JSON())

    assert (
        compare_type(
            None,
            None,
            column,
            JSONB(),
            column.type,
        )
        is None
    )
