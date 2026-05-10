"""0022_lead_agent_state: Lead AI Agent memory column — Sprint 3.1 Phase B.

Revision ID: 0022_lead_agent_state
Revises: 0021_automation_steps
Create Date: 2026-05-10

Adds `leads.agent_state` (JSONB, NOT NULL, DEFAULT '{}') to back the
agent's per-lead memory (SPIN phase, suggestion log, silence alerts,
coach session count). Schema of the JSON payload is owned by
`AgentState` Pydantic model in Phase C — at the DB level the column
is just opaque JSONB so the schema can evolve without a migration.

Existing rows backfill to `'{}'` via the column default. The Sprint
3.1 spec drafted this as migration 0013; by the time 0021
(automation_steps) shipped, the next free index was 0022, not 0023
as the spec speculated.

ADR-020: every new migration starts by widening alembic_version.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_lead_agent_state"
down_revision: Union[str, None] = "0021_automation_steps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    op.add_column(
        "leads",
        sa.Column(
            "agent_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("leads", "agent_state")
