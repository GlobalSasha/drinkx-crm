"""base_update tables: ingest_jobs, ingest_records, ingest_conflicts

Revision ID: 0036_base_update_tables
Revises: 0035_lead_notes_table
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_base_update_tables"
down_revision = "0035_lead_notes_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingest_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_filenames", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stats_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ingest_jobs_workspace_id", "ingest_jobs", ["workspace_id"])
    op.create_index("ix_ingest_jobs_status", "ingest_jobs", ["status"])

    op.create_table(
        "ingest_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ingest_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingest_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False),
        sa.Column("extracted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("match_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(20), nullable=True),
        sa.Column("source_files", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ingest_records_ingest_job_id", "ingest_records", ["ingest_job_id"])
    op.create_index("ix_ingest_records_normalized_name", "ingest_records", ["normalized_name"])

    op.create_table(
        "ingest_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ingest_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingest_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ingest_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingest_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("target_kind", sa.String(20), nullable=False),
        sa.Column("field_name", sa.String(60), nullable=True),
        sa.Column("base_value", sa.Text(), nullable=True),
        sa.Column("incoming_value", sa.Text(), nullable=True),
        sa.Column("candidates_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolved_value", sa.Text(), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ingest_conflicts_ingest_job_id", "ingest_conflicts", ["ingest_job_id"])
    op.create_index("ix_ingest_conflicts_ingest_record_id", "ingest_conflicts", ["ingest_record_id"])
    op.create_index("ix_ingest_conflicts_status", "ingest_conflicts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ingest_conflicts_status", table_name="ingest_conflicts")
    op.drop_index("ix_ingest_conflicts_ingest_record_id", table_name="ingest_conflicts")
    op.drop_index("ix_ingest_conflicts_ingest_job_id", table_name="ingest_conflicts")
    op.drop_table("ingest_conflicts")

    op.drop_index("ix_ingest_records_normalized_name", table_name="ingest_records")
    op.drop_index("ix_ingest_records_ingest_job_id", table_name="ingest_records")
    op.drop_table("ingest_records")

    op.drop_index("ix_ingest_jobs_status", table_name="ingest_jobs")
    op.drop_index("ix_ingest_jobs_workspace_id", table_name="ingest_jobs")
    op.drop_table("ingest_jobs")
