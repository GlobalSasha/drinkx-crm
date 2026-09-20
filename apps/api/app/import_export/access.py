"""Кто что может выгрузить (аудит G6, ревью доступа).

`POST /api/export` принимал `filters` как есть от любого вошедшего
пользователя. Worker ограничивал выборку рабочим пространством — и только
им. Поэтому менеджер мог попросить `assignment_status=pool` и получить всю
базу лидов, которую ему не показывают с 2026-09-14, или подставить
`assigned_to` коллеги и выгрузить чужие карточки.

Правило здесь одно и применяется на сервере ДО создания задачи: в
`filters_json` уходит уже безопасная выборка, а не то, что прислал клиент.
Worker остаётся простым и не обязан ничего перепроверять — но и не
расширяет выборку, потому что расширять уже нечего.

| Роль | Что может выгрузить |
|---|---|
| admin, head | всё рабочее пространство, включая пул; любой `assigned_to` из своего пространства |
| manager | только карточки, закреплённые за ним |

Молчаливого расширения нет: привилегированный фильтр от менеджера — отказ,
а не «выгрузим что-нибудь другое».
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.leads.selection import LeadSelection

PRIVILEGED_ROLES = ("admin", "head")


class ExportFilterForbidden(Exception):
    """403 — роль не даёт права на такую выборку."""


class ExportFilterInvalid(Exception):
    """422 — фильтр ссылается на то, чего нет в этом пространстве."""


def is_privileged(actor: User) -> bool:
    return actor.role in PRIVILEGED_ROLES


async def effective_export_selection(
    db: AsyncSession, raw: dict[str, Any] | None, *, actor: User
) -> LeadSelection:
    """Выборка, которую этому человеку действительно можно выгрузить.

    Возвращает каноническое описание; сохранять в задачу нужно именно его.
    """
    selection = LeadSelection.from_json(raw)

    if is_privileged(actor):
        # Единственное, что проверяется у руководителя: получатель фильтра
        # существует в его пространстве. Иначе фильтр молча не сработал бы
        # (условие по чужому id просто ничего не находит), и человек решил
        # бы, что у сотрудника нет карточек.
        if selection.assigned_to is not None:
            exists = (
                await db.execute(
                    select(User.id).where(
                        User.id == selection.assigned_to,
                        User.workspace_id == actor.workspace_id,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                raise ExportFilterInvalid(
                    "Сотрудник не найден в этом рабочем пространстве"
                )
        return selection

    # --- менеджер --------------------------------------------------------
    # База лидов ему закрыта (политика 2026-09-14), и экспорт не должен
    # быть обходным путём к ней.
    if selection.assignment_status and selection.assignment_status != "assigned":
        raise ExportFilterForbidden(
            "Выгружать базу лидов может только руководитель или админ"
        )
    if selection.assigned_to is not None and selection.assigned_to != actor.id:
        raise ExportFilterForbidden("Выгружать чужие карточки нельзя")

    # Отсутствие `assigned_to` в запросе не означает «всё пространство».
    # Сужаем принудительно — это и есть fail-closed.
    return selection.with_(assigned_to=actor.id, assignment_status="assigned")


def may_read_job(actor: User, job_user_id: uuid.UUID | None) -> bool:
    """Свою задачу экспорта видит автор; руководитель и админ — любую в
    своём пространстве.

    Задачи без автора (старые строки, `user_id` nullable) остаются видны
    только руководству: приписать их кому-то задним числом нельзя, а
    показывать всем — то же расширение доступа, от которого уходим.
    """
    if is_privileged(actor):
        return True
    return job_user_id is not None and job_user_id == actor.id
