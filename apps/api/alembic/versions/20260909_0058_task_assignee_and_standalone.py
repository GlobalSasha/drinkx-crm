"""Задачи: исполнитель + задача без лида (спринт «Руководитель отдела продаж»).

Три изменения в `activities`:
  - `assignee_user_id` — исполнитель задачи. NULL у всех старых строк:
    читаются по-прежнему как «делает владелец лида».
  - `workspace_id` — рабочее пространство. Заполняется только у строк
    без лида; у остальных его даёт сам лид, поэтому backfill не нужен
    и таблица не переписывается.
  - `lead_id` становится nullable — задача может не относиться к лиду.

CHECK гарантирует, что строка всегда чем-то отскоплена: либо лидом,
либо рабочим пространством.

Revision ID: 0058_task_assignee_and_standalone
Revises: 0056_lead_commercial_model

Нумерация: 0057 занята веткой codex/invite-only-access, которая ещё не в
main. Эта ревизия цепляется за 0056 — когда та ветка вольётся, alembic
увидит две головы и понадобится merge-ревизия.
Create Date: 2026-09-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0058_task_assignee_and_standalone"
down_revision: Union[str, None] = "0056_lead_commercial_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("assignee_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_activities_assignee_user_id",
        "activities",
        "users",
        ["assignee_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "activities",
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_activities_workspace_id",
        "activities",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("activities", "lead_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)

    # NOT VALID + отдельная валидация: обычный ADD CONSTRAINT сканирует всю
    # таблицу под ACCESS EXCLUSIVE, а `activities` на проде большая — письма,
    # комментарии, события агента. Контейнер API стартует через
    # `alembic upgrade head`, и на время скана он бы не поднялся.
    op.execute(
        "ALTER TABLE activities ADD CONSTRAINT ck_activities_scope "
        "CHECK (lead_id IS NOT NULL OR workspace_id IS NOT NULL) NOT VALID"
    )
    op.execute("ALTER TABLE activities VALIDATE CONSTRAINT ck_activities_scope")

    # CONCURRENTLY не работает внутри транзакции — выходим из неё на время
    # построения индекса.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_activities_assignee_due "
            "ON activities (assignee_user_id, task_due_at)"
        )


def downgrade() -> None:
    # Строки без лида не переживают откат — удаляем их, иначе NOT NULL
    # на lead_id не встанет.
    op.execute("DELETE FROM activities WHERE lead_id IS NULL")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_activities_assignee_due")
    op.drop_constraint("ck_activities_scope", "activities", type_="check")
    op.alter_column("activities", "lead_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_constraint("fk_activities_workspace_id", "activities", type_="foreignkey")
    op.drop_column("activities", "workspace_id")
    op.drop_constraint("fk_activities_assignee_user_id", "activities", type_="foreignkey")
    op.drop_column("activities", "assignee_user_id")
