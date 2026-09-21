"""Alembic env — async, with metadata from app models."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import settings + Base + ALL models so metadata is populated.
# Список моделей один на проект — app/models_registry.py. Раньше он дублировался
# здесь вручную и отставал от дерева. target_metadata — тот же Base.metadata.
from app.config import get_settings
from app.models_registry import Base  # noqa: F401 — импорт наполняет metadata
from scripts.alembic_drift_policy import (
    compare_server_default,
    compare_type,
    include_object,
)

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
        compare_type=compare_type,
        compare_server_default=compare_server_default,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


# Alembic's bookkeeping column is too narrow for this project's revision ids.
# The reasoning, and why the check has to look before it writes, live in
# scripts/alembic_version_table.py. `prepend_sys_path = .` in alembic.ini puts
# apps/api on sys.path, which is how `app.config` above is importable too.
from scripts.alembic_version_table import (  # noqa: E402
    CREATED,
    UNCHANGED,
    ensure_version_table_width,
)

# Commands that only read. `alembic current` is a status query; it has no
# business creating or altering tables on the way to answering (finding R3).
READ_ONLY_COMMANDS = frozenset({"current", "heads", "history", "show", "branches"})


def _alembic_command_name() -> str | None:
    """The subcommand being run, or None when Alembic is driven in-process."""
    cmd = getattr(getattr(config, "cmd_opts", None), "cmd", None)
    if not cmd:
        return None
    return getattr(cmd[0], "__name__", None)


def do_run_migrations(connection: Connection) -> None:
    command_name = _alembic_command_name()
    if command_name in READ_ONLY_COMMANDS:
        # Read-only: report what is there, change nothing. A narrow column will
        # be widened by the next command that actually writes.
        pass
    else:
        action = ensure_version_table_width(connection)
        if action != UNCHANGED:
            verb = "created" if action == CREATED else "widened"
            print(f"alembic: {verb} the {'' if action == CREATED else 'existing '}"
                  f"version table so it can hold this project's revision ids")

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=compare_type,
        compare_server_default=compare_server_default,
        include_object=include_object,
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
