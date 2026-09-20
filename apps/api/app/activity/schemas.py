"""Pydantic schemas for Activity endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: str
    payload_json: dict = Field(default_factory=dict)
    task_due_at: datetime | None = None
    # Исполнитель задачи. Пусто = «делает владелец лида» — так задачи
    # вели себя до появления поля. Назначить задачу другому человеку
    # может только руководитель или админ (проверка в сервисе).
    assignee_user_id: UUID | None = None
    reminder_trigger_at: datetime | None = None
    file_url: str | None = None
    file_kind: str | None = None
    channel: str | None = None
    direction: str | None = None
    subject: str | None = None
    body: str | None = None
    # Email-specific (Sprint 2.0). Surfaces in Lead Card Activity Feed
    # via the email-renderer branch in apps/web; ADR-019 keeps these
    # lead-scoped (no per-user filtering).
    from_identifier: str | None = None
    to_identifier: str | None = None
    gmail_message_id: str | None = None


class ActivityCreate(ActivityBase):
    pass


class TaskUpdateIn(BaseModel):
    model_config = ConfigDict()

    body: str | None = Field(None, max_length=2000)
    task_due_at: datetime | None = None


class CommentUpdateIn(BaseModel):
    """Body for PATCH /leads/{id}/activities/{id}/comment — edit a
    manager comment's text. Author-or-admin only (enforced server-side)."""

    model_config = ConfigDict()

    body: str = Field(min_length=1, max_length=4000)


class ActivityOut(ActivityBase):
    id: UUID
    lead_id: UUID
    user_id: UUID | None
    task_done: bool
    task_completed_at: datetime | None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ActivityListOut(BaseModel):
    items: list[ActivityOut]
    next_cursor: str | None  # ISO timestamp of last item's created_at, or None when no more


class FeedItemOut(ActivityOut):
    """Activity enriched with the resolved author name for the
    unified feed (`GET /leads/{id}/feed`). Same shape as `ActivityOut`
    plus `author_name` — fetched via LEFT JOIN on `users` in the
    feed repository so the frontend doesn't N+1 across the page.

    For `type='ai_suggestion'` rows, `author_name` is forced to
    "Блейк" regardless of `user_id` (the runner / chat handler may
    leave user_id NULL or stamp the manager who triggered the
    refresh; either way the feed presents Блейк as the speaker).
    """

    author_name: str | None = None


class FeedListOut(BaseModel):
    items: list[FeedItemOut]
    next_cursor: str | None
    has_more: bool


class MyTaskOut(BaseModel):
    """Одна задача, заведённая руками (Activity type=task), для списков
    `GET /me/tasks` и `GET /tasks`. Без AI-полей — задачи только ручные.

    `lead_id` может быть пустым: задача не обязана относиться к лиду.
    `assignee_*` — уже разрешённый исполнитель: явный, иначе владелец
    лида, иначе автор.
    """

    id: UUID
    lead_id: UUID | None = None
    lead_company_name: str | None = None
    text: str
    task_due_at: datetime | None = None
    task_done: bool
    task_completed_at: datetime | None = None
    created_at: datetime
    assignee_user_id: UUID | None = None
    assignee_name: str | None = None
    # Значение, записанное в самой строке, до применения лестницы. Карточке
    # лида оно нужно для селектора «Поручить»: пустой выбор там означает
    # «делает владелец лида», и подстановка вычисленного владельца превратила
    # бы неявное назначение в явное при первом же сохранении.
    explicit_assignee_user_id: UUID | None = None
    author_user_id: UUID | None = None
    author_name: str | None = None


class TaskCountsOut(BaseModel):
    """Размеры полной серверной выборки, а не загруженной страницы.

    С постраничной выдачей счётчик по загруженным строкам просто врёт:
    «12 из 50 выполнено» на первой странице из трёхсот задач — это не про
    работу человека, а про размер страницы.
    """

    total: int
    open: int
    done: int
    overdue: int


class TaskListOut(BaseModel):
    """Ответ всех списков задач: `/tasks`, `/me/tasks`, `/leads/{id}/tasks`.

    `next_cursor` пуст, когда страница последняя. Курсор непрозрачный:
    это полный ключ сортировки последней строки, и разбирать его на клиенте
    не нужно — только вернуть как есть.
    """

    items: list[MyTaskOut]
    next_cursor: str | None = None
    counts: TaskCountsOut


class TaskCreateIn(BaseModel):
    """Body for POST /tasks — задача с исполнителем и, по желанию, лидом."""

    text: str = Field(min_length=1, max_length=2000)
    task_due_at: datetime | None = None
    assignee_user_id: UUID | None = None
    lead_id: UUID | None = None


class TaskPatchIn(BaseModel):
    """Body for PATCH /tasks/{id}. Передавайте только меняемые поля."""

    text: str | None = Field(None, min_length=1, max_length=2000)
    task_due_at: datetime | None = None
    assignee_user_id: UUID | None = None


class AskBlakeIn(BaseModel):
    """Body for POST /leads/{id}/feed/ask-blake."""

    question: str = Field(min_length=1, max_length=4000)


class AskBlakeOut(BaseModel):
    """Returns both freshly-inserted activities so the frontend can
    append them optimistically (without a feed refetch round-trip)."""

    question_activity: FeedItemOut
    answer_activity: FeedItemOut
