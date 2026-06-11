"""Lead lookup indexes — tg_chat_id, max_user_id, assigned_to, needs_review.

Speeds up inbox channel-id matching, manager portfolio group-bys, and the
leads-pool needs_review filter. All workspace-scoped composite indexes.

Revision ID: 0048_lead_lookup_indexes
Revises: 0047_user_forms_inbox_seen
Create Date: 2026-06-11
"""
from alembic import op

revision = "0048_lead_lookup_indexes"
down_revision = "0047_user_forms_inbox_seen"
branch_labels = None
depends_on = None

_INDEXES = [
    ("ix_leads_workspace_tg_chat_id", ["workspace_id", "tg_chat_id"]),
    ("ix_leads_workspace_max_user_id", ["workspace_id", "max_user_id"]),
    ("ix_leads_workspace_assigned_to", ["workspace_id", "assigned_to"]),
    ("ix_leads_workspace_needs_review", ["workspace_id", "needs_review"]),
]


def upgrade() -> None:
    for name, cols in _INDEXES:
        op.create_index(name, "leads", cols)


def downgrade() -> None:
    for name, _cols in reversed(_INDEXES):
        op.drop_index(name, table_name="leads")
