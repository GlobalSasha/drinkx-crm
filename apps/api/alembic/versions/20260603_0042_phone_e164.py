"""phone_e164: E.164-normalized phone on leads + contacts (dedup / matching key).

Adds a nullable, indexed `phone_e164` column to both `leads` and `contacts`.
Filled from the existing `phone` column on write via a SQLAlchemy @validates
hook (see app/leads/models.py, app/contacts/models.py). Existing rows stay NULL
until the next save — a one-time backfill can run later (it needs the
`phonenumbers` library, so it lives in app code, not raw SQL).

Revision ID: 0042_phone_e164
Revises: 0041_webform_routing_intake
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0042_phone_e164"
down_revision = "0041_webform_routing_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("phone_e164", sa.String(length=20), nullable=True))
    op.create_index("ix_leads_phone_e164", "leads", ["phone_e164"])
    op.add_column("contacts", sa.Column("phone_e164", sa.String(length=20), nullable=True))
    op.create_index("ix_contacts_phone_e164", "contacts", ["phone_e164"])


def downgrade() -> None:
    op.drop_index("ix_contacts_phone_e164", table_name="contacts")
    op.drop_column("contacts", "phone_e164")
    op.drop_index("ix_leads_phone_e164", table_name="leads")
    op.drop_column("leads", "phone_e164")
