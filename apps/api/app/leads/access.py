"""Кто может открыть этот лид.

Правило одно на всё приложение: руководитель и админ читают любой лид своего
рабочего пространства, менеджер — только тот, что закреплён за ним. Чужой лид
и лид другого пространства неотличимы: и там и там 404, потому что 403 сам по
себе подтверждает, что такой лид существует.

Живёт отдельным модулем, а не внутри `app/leads/routers.py`, потому что
пользователей у правила двое: сам роутер `/leads` и `/leads/{id}/tasks` из
`app/activity/routers.py`. Второй подключается отдельно от первого, поэтому
страж роутера `/leads` на него не распространялся, и менеджер мог прочитать
задачи чужого лида, зная его UUID (аудит G5, ревью).
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")


async def lead_access_guard(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> None:
    """Страж уровня роутера: каждый нынешний и будущий маршрут с `{lead_id}`
    закрыт по построению, а не потому, что кто-то не забыл дописать проверку
    в обработчике."""
    lead_id = request.path_params.get("lead_id")
    if lead_id is None:
        return
    if user.role in ("admin", "head"):
        return
    from app.leads.repositories import get_by_id

    try:
        lead_uuid = UUID(str(lead_id))
    except ValueError:
        raise _not_found()
    lead = await get_by_id(db, lead_uuid, user.workspace_id)
    if lead is None or lead.assigned_to != user.id:
        raise _not_found()
