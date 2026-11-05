"""@-упоминания в комментариях: кого нашли и кому пришло уведомление."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.activity.mentions import find_mentions
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


def _user(name):
    return SimpleNamespace(id=uuid.uuid4(), name=name)


def test_find_mentions_rules():
    kirill, dima, vlada = _user("Кирилл"), _user("Dmitriy Onischuk"), _user("Влада")
    users = [kirill, dima, vlada]

    assert find_mentions("@кирилл, что с лидом?", users) == [kirill]
    assert find_mentions("@Dmitriy Onischuk и @Влада", users) == [dima, vlada]
    # Повтор — один человек; почта, продолжение слова и пустой текст — никто.
    assert find_mentions("@Влада @Влада", users) == [vlada]
    assert find_mentions("vlada a@Влада @Владами", users) == []
    assert find_mentions(None, users) == []


def test_longer_name_wins_over_its_prefix():
    anna, anna_maria = _user("Анна"), _user("Анна Мария")
    assert find_mentions("@Анна Мария", [anna, anna_maria]) == [anna_maria]


async def _setup(db, workspace, user):
    from app.auth.models import User
    from app.leads import repositories as leads_repo

    head = User(workspace_id=workspace.id, email=f"h-{uuid.uuid4().hex[:8]}@t.com",
                name="Кирилл", role="head")
    owner = User(workspace_id=workspace.id, email=f"o-{uuid.uuid4().hex[:8]}@t.com",
                 name="Влада", role="manager")
    db.add_all([head, owner])
    await db.flush()
    lead = await leads_repo.create_lead(
        db, workspace.id, {"company_name": "Лента"},
        assigned_to=owner.id, assignment_status="assigned",
    )
    return head, owner, lead


async def _notes(db, user_id):
    from app.notifications.models import Notification

    return (
        await db.execute(select(Notification).where(Notification.user_id == user_id))
    ).scalars().all()


@skip_no_pg
@pytest.mark.asyncio
async def test_comment_notifies_mentioned_every_time(db, workspace, user):
    from app.activity import services

    head, owner, lead = await _setup(db, workspace, user)
    for body in ("@Влада что с договором?", "@Влада и счёт тоже"):
        await services.create_activity(
            db, workspace.id, lead.id, head, {"type": "comment", "body": body}
        )

    notes = await _notes(db, owner.id)
    assert len(notes) == 2  # часовое окно повторов упоминания не глушит
    assert notes[0].kind == "mention" and notes[0].lead_id == lead.id
    assert "Лента" in notes[0].title and "Кирилл:" in notes[0].body


@skip_no_pg
@pytest.mark.asyncio
async def test_author_and_outsider(db, workspace, user):
    from app.activity import services

    head, owner, lead = await _setup(db, workspace, user)
    # `user` из фикстуры — менеджер без доступа к чужому лиду, зовут Manager.
    await services.create_activity(
        db, workspace.id, lead.id, head,
        {"type": "comment", "body": "@Кирилл @Manager посмотрите"},
    )

    assert await _notes(db, head.id) == []
    outsider = await _notes(db, user.id)
    assert len(outsider) == 1 and outsider[0].lead_id is None


@skip_no_pg
@pytest.mark.asyncio
async def test_edit_notifies_only_newly_mentioned(db, workspace, user):
    from app.activity import services

    head, owner, lead = await _setup(db, workspace, user)
    comment = await services.create_activity(
        db, workspace.id, lead.id, head, {"type": "comment", "body": "@Влада вопрос"}
    )
    await services.update_comment(
        db, workspace.id, lead.id, comment.id, actor=head,
        body="@Влада @Manager вопрос",
    )

    assert len(await _notes(db, owner.id)) == 1
    assert len(await _notes(db, user.id)) == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_task_text_does_not_mention(db, workspace, user):
    from app.activity import services

    head, owner, lead = await _setup(db, workspace, user)
    await services.create_activity(
        db, workspace.id, lead.id, head,
        {"type": "task", "body": "@Manager позвонить", "assignee_user_id": owner.id},
    )
    assert await _notes(db, user.id) == []
