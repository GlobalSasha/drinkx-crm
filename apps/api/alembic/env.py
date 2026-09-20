"""Alembic env — async, with metadata from app models."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import settings + Base + ALL models so metadata is populated.
from app.config import get_settings
from app.common.models import Base
from app.auth import models as _auth_models  # noqa: F401
from app.base_update import models as _base_update_models  # noqa: F401
from app.pipelines import models as _pipeline_models  # noqa: F401
from app.leads import models as _leads_models        # noqa: F401
from app.contacts import models as _contacts_models  # noqa: F401
from app.activity import models as _activity_models  # noqa: F401
from app.followups import models as _followups_models  # noqa: F401
from app.enrichment import models as _enrichment_models  # noqa: F401
from app.daily_plan import models as _daily_plan_models  # noqa: F401
from app.notifications import models as _notifications_models  # noqa: F401
from app.audit import models as _audit_models  # noqa: F401
from app.inbox import models as _inbox_models  # noqa: F401
from app.import_export import models as _import_export_models  # noqa: F401
from app.forms import models as _forms_models  # noqa: F401
from app.custom_attributes import models as _custom_attr_models  # noqa: F401
from app.template import models as _template_models  # noqa: F401
from app.automation_builder import models as _automation_builder_models  # noqa: F401
from app.quotas import models as _quotas_models  # noqa: F401
from app.utm import models as _utm_models  # noqa: F401
from app.presence import models as _presence_models  # noqa: F401

config = context.config

# Override sqlalchemy.url with the env-driven setting (sync URL — Alembic uses sync engine internally
# unless we go async, which we do below).
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# Alembic hardcodes `Column("version_num", String(32))` for its bookkeeping
# table (alembic/ddl/impl.py, version_table_impl) and exposes no option to
# widen it. Seven revision ids in this project are longer than 32 characters —
# the first is `0009_inbox_items_and_activity_email` at 35 — so `upgrade head`
# against a NEW database dies there with:
#
#   StringDataRightTruncationError: value too long for type character varying(32)
#
# which means the chain could not build a fresh environment at all: disaster
# recovery, a new staging box, or a wiped volume would never come up, because
# the API container runs `alembic upgrade head` before uvicorn starts.
#
# Create the table ourselves at a workable width, and widen it if an older
# database already has the narrow one. Idempotent, one row, Alembic's
# `create(checkfirst=True)` then leaves our table alone. The alternative —
# renaming seven historical revisions — rewrites migration history that live
# databases already point at.
VERSION_NUM_WIDTH = 255


def _ensure_wide_version_table(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        f"version_num VARCHAR({VERSION_NUM_WIDTH}) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    )
    connection.exec_driver_sql(
        "ALTER TABLE alembic_version "
        f"ALTER COLUMN version_num TYPE VARCHAR({VERSION_NUM_WIDTH})"
    )
    # Commit and leave the connection with no transaction open. Alembic's
    # begin_transaction() treats an already-active transaction as "someone else
    # owns this" and hands back a no-op, which then breaks the autocommit_block
    # a couple of migrations use for CREATE INDEX CONCURRENTLY.
    connection.commit()


def do_run_migrations(connection: Connection) -> None:
    _ensure_wide_version_table(connection)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
