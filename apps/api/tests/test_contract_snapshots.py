"""Снимок ключей ответов, которые читает фронтенд (ARCH-03).

DRIFT-1 держался ровно на том, что схему списка и её читателя ничто не
сверяло: `ai_data` из `LeadListItemOut` убрали, компонент продолжил его
читать, и бейдж молча показывал ноль. Здесь набор полей зафиксирован
буквально — поле, пропавшее или появившееся без правки `apps/web/lib/types.ts`,
роняет тест, а не экран.

Красный тест — не «почини», а «обнови обе стороны разом»: список ниже,
соответствующий тип во фронтенде и его фикстуры.
"""
from __future__ import annotations

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy

LEAD_LIST_ITEM_KEYS = {
    "id", "workspace_id", "pipeline_id", "stage_id", "company_name", "segment",
    "city", "email", "phone", "website", "inn", "source", "source_id",
    "tags_json", "deal_type", "priority", "priority_label", "score",
    "fit_score", "blocker", "next_step", "next_action_at",
    "assignment_status", "assigned_to", "assigned_at", "transferred_from",
    "transferred_at", "is_rotting_stage", "is_rotting_next_step",
    "last_activity_at", "archived_at", "won_at", "lost_at", "lost_reason",
    "deleted_at", "primary_contact_id", "primary_contact_name",
    "source_form_id", "source_form_name", "latest_utm",
    "open_followups_count", "open_tasks_count", "commercial_model",
    "deal_amount", "deal_quantity", "deal_equipment", "needs_review",
    # Одно число вместо всего ai_data — см. test_arch03_ai_confidence.py.
    "ai_confidence",
    "created_at", "updated_at",
}

MY_TASK_KEYS = {
    "id", "text", "task_due_at", "task_done", "task_completed_at",
    "lead_id", "lead_company_name", "assignee_user_id", "assignee_name",
    "explicit_assignee_user_id", "author_user_id", "author_name",
    "created_at",
}


def test_lead_list_item_keys_are_frozen():
    from app.leads.schemas import LeadListItemOut

    assert set(LeadListItemOut.model_fields) == LEAD_LIST_ITEM_KEYS
    # Тяжёлый AI-payload в списке не появляется даже случайно.
    assert "ai_data" not in LeadListItemOut.model_fields
    assert "agent_state" not in LeadListItemOut.model_fields
    # `current_stage_days` считает только карточка лида.
    assert "current_stage_days" not in LeadListItemOut.model_fields


def test_task_list_keys_are_frozen():
    from app.activity.schemas import MyTaskOut, TaskListOut

    assert set(TaskListOut.model_fields) == {"items", "counts", "next_cursor"}
    assert set(MyTaskOut.model_fields) == MY_TASK_KEYS
