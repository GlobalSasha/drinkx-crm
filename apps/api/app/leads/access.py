"""Кто может открыть этот лид и его дочерние записи.

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


def may_access_lead(user: User, lead) -> bool:
    """Одно правило на всё приложение, в виде чистой функции."""
    if lead is None:
        return False
    if user.role in ("admin", "head"):
        return lead.workspace_id == user.workspace_id
    return lead.workspace_id == user.workspace_id and lead.assigned_to == user.id


async def ensure_lead_access(db: AsyncSession, *, lead_id, user: User):
    """Проверка доступа к лиду для обработчиков, которым путь к нему даёт
    не сам путь, а дочерний объект.

    Страж роутера закрывает маршруты вида `/leads/{lead_id}/…`. Но у части
    маршрутов в пути только идентификатор дочерней записи — КП, файла,
    активности, — и тогда лид достаётся из неё, а право на него надо
    проверить отдельно. Иначе достаточно знать UUID КП, чтобы прочитать и
    переписать его, минуя карточку.

    Возвращает лид, если доступ есть. Иначе 404: «нет такого» и «есть, но
    не ваш» должны отвечать одинаково.
    """
    from app.leads.repositories import get_by_id

    if lead_id is None:
        return None
    lead = await get_by_id(db, lead_id, user.workspace_id)
    if not may_access_lead(user, lead):
        raise _not_found()
    return lead


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
        # Роутер может нести и маршруты без лида в пути (например,
        # `/api/quotes/{quote_id}`). Их закрывает не этот страж, а проверка
        # по владельцу дочернего объекта в самом обработчике.
        return
    try:
        lead_uuid = UUID(str(lead_id))
    except ValueError:
        raise _not_found()
    # Руководитель и админ раньше проходили здесь без единого запроса: их
    # пропускали, полагаясь на то, что обработчик сам сузит выборку
    # пространством. Большинство обработчиков так и делает, но не все —
    # `/leads/{id}/inbox` отдавал переписку админу ЧУЖОГО пространства
    # (аудит SEC-01-L). Теперь пространство проверяется для всех ролей:
    # один лишний запрос против межпространственной утечки.
    await ensure_lead_access(db, lead_id=lead_uuid, user=user)
