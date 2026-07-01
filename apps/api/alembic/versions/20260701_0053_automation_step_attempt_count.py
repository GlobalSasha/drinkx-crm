"""Automation step-run attempt_count: bounded retry for transient failures.

Adds `attempt_count` to `automation_step_runs` (plan 015). Nullable-free,
additive with a server default of 0 — existing rows and the scheduler's
current `failed`-on-first-error behaviour are unaffected until the retry
logic in `execute_due_step_runs` starts bumping it.

Revision ID: 0053_automation_step_attempt_count
Revises: 0052_lead_soft_delete
Create Date: 2026-07-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0053_automation_step_attempt_count"
down_revision = "0052_lead_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_step_runs",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("automation_step_runs", "attempt_count")
