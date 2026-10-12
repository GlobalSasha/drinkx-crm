"""Per-manager access to the free lead pool."""
import sqlalchemy as sa

from alembic import op

revision = "0059_user_lead_pool_access"
down_revision = "0057_user_invite_expires_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_access_lead_pool", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "can_access_lead_pool")
