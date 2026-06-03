"""email_normalized + email_domain_criterion dedup keys on leads (+ contacts).

Adds normalized-email columns used for duplicate detection (Odoo dedup pattern):
  • leads.email_normalized          — lower-cased full email
  • leads.email_domain_criterion    — corporate domain (free-mail excluded)
  • contacts.email_normalized       — lower-cased full email
All nullable + indexed, filled from `email` on write via @validates hooks.
Additive and safe; existing rows stay NULL until their next save.

Revision ID: 0043_email_dedup_keys
Revises: 0042_phone_e164
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0043_email_dedup_keys"
down_revision = "0042_phone_e164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("email_normalized", sa.String(length=254), nullable=True))
    op.add_column("leads", sa.Column("email_domain_criterion", sa.String(length=255), nullable=True))
    op.create_index("ix_leads_email_normalized", "leads", ["email_normalized"])
    op.create_index("ix_leads_email_domain_criterion", "leads", ["email_domain_criterion"])

    op.add_column("contacts", sa.Column("email_normalized", sa.String(length=254), nullable=True))
    op.create_index("ix_contacts_email_normalized", "contacts", ["email_normalized"])


def downgrade() -> None:
    op.drop_index("ix_contacts_email_normalized", table_name="contacts")
    op.drop_column("contacts", "email_normalized")

    op.drop_index("ix_leads_email_domain_criterion", table_name="leads")
    op.drop_index("ix_leads_email_normalized", table_name="leads")
    op.drop_column("leads", "email_domain_criterion")
    op.drop_column("leads", "email_normalized")
