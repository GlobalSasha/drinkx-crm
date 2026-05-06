"""0002_b2b_model: 11-stage B2B pipeline + lead layer

Revision ID: 0002_b2b_model
Revises: 0001_initial
Create Date: 2026-05-06
"""
from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_b2b_model"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Constants — do NOT import app models here
# ---------------------------------------------------------------------------

_B2B_STAGES = [
    {"name": "Новый контакт",      "position": 0,  "color": "#a1a1a6", "rot_days": 3,  "probability": 5,   "is_won": False, "is_lost": False},
    {"name": "Квалификация",       "position": 1,  "color": "#0a84ff", "rot_days": 5,  "probability": 15,  "is_won": False, "is_lost": False},
    {"name": "Discovery",          "position": 2,  "color": "#5e5ce6", "rot_days": 7,  "probability": 25,  "is_won": False, "is_lost": False},
    {"name": "Solution Fit",       "position": 3,  "color": "#bf5af2", "rot_days": 7,  "probability": 40,  "is_won": False, "is_lost": False},
    {"name": "Business Case / КП", "position": 4,  "color": "#ff9f0a", "rot_days": 5,  "probability": 50,  "is_won": False, "is_lost": False},
    {"name": "Multi-stakeholder",  "position": 5,  "color": "#ff6b00", "rot_days": 7,  "probability": 60,  "is_won": False, "is_lost": False},
    {"name": "Договор / пилот",    "position": 6,  "color": "#ff3b30", "rot_days": 5,  "probability": 75,  "is_won": False, "is_lost": False},
    {"name": "Производство",       "position": 7,  "color": "#ff2d55", "rot_days": 10, "probability": 85,  "is_won": False, "is_lost": False},
    {"name": "Пилот",              "position": 8,  "color": "#34c759", "rot_days": 14, "probability": 90,  "is_won": False, "is_lost": False},
    {"name": "Scale / серия",      "position": 9,  "color": "#30d158", "rot_days": 14, "probability": 95,  "is_won": False, "is_lost": False},
    {"name": "Закрыто (won)",      "position": 10, "color": "#32d74b", "rot_days": 0,  "probability": 100, "is_won": True,  "is_lost": False},
    {"name": "Закрыто (lost)",     "position": 11, "color": "#ff3b30", "rot_days": 0,  "probability": 0,   "is_won": False, "is_lost": True},
]

_GATE_CRITERIA: dict[int, list[str]] = {
    1: ["ICP соответствие подтверждено", "ЛПР идентифицирован", "Сегмент и тип сделки определены", "Приоритет A/B/C/D присвоен"],
    2: ["Проведён discovery-звонок (≥30 мин)", "Боль/потребность зафиксирована", "Бюджет предварительно обсуждён"],
    3: ["Solution fit подтверждён", "Pilot feasibility оценена", "Технический покупатель вовлечён"],
    4: ["КП отправлено", "ROI-расчёт согласован", "Следующий шаг назначен с датой"],
    5: ["Экономический покупатель идентифицирован", "Все стейкхолдеры вовлечены", "Внутренний чемпион активен"],
    6: ["Договор отправлен", "Юридическое согласование начато", "Пилот-план согласован"],
    7: ["Договор подписан", "Производство запущено", "Pilot Success Contract заполнен"],
    8: ["Оборудование доставлено", "Установка подтверждена", "Пилотные цели зафиксированы"],
    9: ["Пилот завершён", "KPI зафиксированы", "Решение о масштабировании принято"],
    10: [],
}

_SCORING_CRITERIA = [
    {"criterion_key": "scale_potential",       "label": "Масштаб потенциала",       "weight": 20, "max_value": 5},
    {"criterion_key": "pilot_probability_90d", "label": "Вероятность пилота 90д",   "weight": 15, "max_value": 5},
    {"criterion_key": "economic_buyer",        "label": "Экономический покупатель", "weight": 15, "max_value": 5},
    {"criterion_key": "reference_value",       "label": "Референсная ценность",     "weight": 15, "max_value": 5},
    {"criterion_key": "standard_product",      "label": "Стандартный продукт",      "weight": 10, "max_value": 5},
    {"criterion_key": "data_readiness",        "label": "Готовность данных",        "weight": 10, "max_value": 5},
    {"criterion_key": "partner_potential",     "label": "Партнёрский потенциал",    "weight": 10, "max_value": 5},
    {"criterion_key": "budget_confirmed",      "label": "Бюджет подтверждён",       "weight": 5,  "max_value": 5},
]


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Add gate_criteria_json to stages
    # ------------------------------------------------------------------
    op.add_column(
        "stages",
        sa.Column(
            "gate_criteria_json",
            postgresql.JSON,
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )

    # ------------------------------------------------------------------
    # 2. Data migration: re-seed default pipeline stages with B2B stages
    # ------------------------------------------------------------------
    pipelines = conn.execute(
        sa.text("SELECT id FROM pipelines WHERE is_default = TRUE")
    ).fetchall()

    for (pipeline_id,) in pipelines:
        conn.execute(
            sa.text("DELETE FROM stages WHERE pipeline_id = :pid"),
            {"pid": str(pipeline_id)},
        )
        for stage in _B2B_STAGES:
            gate_criteria = _GATE_CRITERIA.get(stage["position"], [])
            conn.execute(
                sa.text(
                    "INSERT INTO stages "
                    "(id, created_at, updated_at, pipeline_id, name, position, color, "
                    "rot_days, probability, is_won, is_lost, gate_criteria_json) "
                    "VALUES (:id, now(), now(), :pipeline_id, :name, :position, :color, "
                    ":rot_days, :probability, :is_won, :is_lost, CAST(:gate_criteria_json AS json))"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pipeline_id": str(pipeline_id),
                    "name": stage["name"],
                    "position": stage["position"],
                    "color": stage["color"],
                    "rot_days": stage["rot_days"],
                    "probability": stage["probability"],
                    "is_won": stage["is_won"],
                    "is_lost": stage["is_lost"],
                    "gate_criteria_json": json.dumps(gate_criteria, ensure_ascii=False),
                },
            )

    # ------------------------------------------------------------------
    # 3. Create scoring_criteria table
    # ------------------------------------------------------------------
    op.create_table(
        "scoring_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criterion_key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("weight", sa.Integer, nullable=False),
        sa.Column("max_value", sa.Integer, nullable=False, server_default="5"),
        sa.UniqueConstraint("workspace_id", "criterion_key", name="uq_scoring_criteria_workspace_key"),
    )
    op.create_index("ix_scoring_criteria_workspace_id", "scoring_criteria", ["workspace_id"])

    # ------------------------------------------------------------------
    # 4. Data migration: seed scoring_criteria for all existing workspaces
    # ------------------------------------------------------------------
    workspaces = conn.execute(sa.text("SELECT id FROM workspaces")).fetchall()
    for (workspace_id,) in workspaces:
        for criterion in _SCORING_CRITERIA:
            conn.execute(
                sa.text(
                    "INSERT INTO scoring_criteria "
                    "(id, workspace_id, criterion_key, label, weight, max_value) "
                    "VALUES (:id, :workspace_id, :criterion_key, :label, :weight, :max_value)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "workspace_id": str(workspace_id),
                    "criterion_key": criterion["criterion_key"],
                    "label": criterion["label"],
                    "weight": criterion["weight"],
                    "max_value": criterion["max_value"],
                },
            )

    # ------------------------------------------------------------------
    # 5. Create leads table
    # ------------------------------------------------------------------
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pipelines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("stages.id", ondelete="SET NULL"), nullable=True),
        # Basic
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("segment", sa.String(60), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("inn", sa.String(20), nullable=True),
        sa.Column("source", sa.String(60), nullable=True),
        sa.Column("tags_json", postgresql.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        # B2B
        sa.Column("deal_type", sa.String(30), nullable=True),
        sa.Column("priority", sa.String(2), nullable=True),
        sa.Column("score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fit_score", sa.Numeric(4, 2), nullable=True),
        # Lead Pool
        sa.Column("assignment_status", sa.String(20), nullable=False, server_default="pool"),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transferred_from", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transferred_at", sa.DateTime(timezone=True), nullable=True),
        # Rotting
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_rotting_stage", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_rotting_next_step", sa.Boolean, nullable=False, server_default=sa.false()),
        # Pilot
        sa.Column("pilot_contract_json", postgresql.JSON, nullable=True),
        # Lifecycle
        sa.Column("blocker", sa.String(500), nullable=True),
        sa.Column("next_step", sa.String(500), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("won_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.String(500), nullable=True),
        sa.Column("ai_data", postgresql.JSON, nullable=True),
    )
    op.create_index("ix_leads_workspace_id", "leads", ["workspace_id"])
    op.create_index("ix_leads_workspace_stage", "leads", ["workspace_id", "stage_id"])
    op.create_index("ix_leads_workspace_assignment", "leads", ["workspace_id", "assignment_status"])
    op.create_index("ix_leads_rotting", "leads", ["is_rotting_stage", "is_rotting_next_step"])

    # GIN full-text index on company_name
    conn.execute(
        sa.text(
            "CREATE INDEX ix_leads_company_name_fts ON leads "
            "USING GIN (to_tsvector('simple', company_name))"
        )
    )

    # ------------------------------------------------------------------
    # 6. Create contacts table
    # ------------------------------------------------------------------
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("role_type", sa.String(30), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("telegram_url", sa.String(255), nullable=True),
        sa.Column("linkedin_url", sa.String(255), nullable=True),
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("verified_status", sa.String(20), nullable=False, server_default="to_verify"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_contacts_lead_id", "contacts", ["lead_id"])

    # ------------------------------------------------------------------
    # 7. Create activities table
    # ------------------------------------------------------------------
    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("payload_json", postgresql.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("task_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_done", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("task_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_trigger_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("file_kind", sa.String(40), nullable=True),
        sa.Column("channel", sa.String(20), nullable=True),
        sa.Column("direction", sa.String(10), nullable=True),
        sa.Column("subject", sa.String(300), nullable=True),
        sa.Column("body", sa.Text, nullable=True),
    )
    op.create_index("ix_activities_lead_id", "activities", ["lead_id"])
    op.create_index("ix_activities_lead_type", "activities", ["lead_id", "type"])

    # ------------------------------------------------------------------
    # 8. Create followups table
    # ------------------------------------------------------------------
    op.create_table(
        "followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reminder_kind", sa.String(20), nullable=False, server_default="manager"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_followups_lead_id", "followups", ["lead_id"])


def downgrade() -> None:
    conn = op.get_bind()

    op.drop_index("ix_followups_lead_id", table_name="followups")
    op.drop_table("followups")

    op.drop_index("ix_activities_lead_type", table_name="activities")
    op.drop_index("ix_activities_lead_id", table_name="activities")
    op.drop_table("activities")

    op.drop_index("ix_contacts_lead_id", table_name="contacts")
    op.drop_table("contacts")

    conn.execute(sa.text("DROP INDEX IF EXISTS ix_leads_company_name_fts"))
    op.drop_index("ix_leads_rotting", table_name="leads")
    op.drop_index("ix_leads_workspace_assignment", table_name="leads")
    op.drop_index("ix_leads_workspace_stage", table_name="leads")
    op.drop_index("ix_leads_workspace_id", table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_scoring_criteria_workspace_id", table_name="scoring_criteria")
    op.drop_table("scoring_criteria")

    op.drop_column("stages", "gate_criteria_json")
