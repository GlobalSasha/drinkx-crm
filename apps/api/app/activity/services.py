"""Activity service layer — business validation on top of repositories."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import repositories as repo
from app.activity.models import Activity, ActivityType
from app.auth.models import User
from app.leads import repositories as leads_repo
from app.leads.services import LeadNotFound

_VALID_TYPES = {t.value for t in ActivityType}


class ActivityNotFound(Exception):
    pass


class ActivityWrongType(Exception):
    pass


class ActivityForbidden(Exception):
    """Caller is neither the activity's author nor an admin."""


def _validate_type(type_: str) -> None:
    if type_ not in _VALID_TYPES:
        raise ValueError(f"Invalid activity type '{type_}'. Allowed: {_VALID_TYPES}")


def _task_row_to_dict(
    activity: Activity, lead, assignee_name, owner_name, author_name
) -> dict:
    """Строка задачи в том виде, в каком её ждёт API. Текст лежит либо в
    payload_json.title (так пишет форма задачи), либо в body.

    Имя исполнителя идёт по той же лестнице, что и `effective_assignee_id`:
    явный исполнитель → владелец лида → автор.
    """
    return {
        "id": activity.id,
        "lead_id": activity.lead_id,
        "lead_company_name": lead.company_name if lead is not None else None,
        "text": (activity.payload_json or {}).get("title") or activity.body or "Задача",
        "task_due_at": activity.task_due_at,
        "task_done": activity.task_done,
        "task_completed_at": activity.task_completed_at,
        "created_at": activity.created_at,
        "assignee_user_id": effective_assignee_id(activity, lead),
        "assignee_name": assignee_name or owner_name or author_name,
        # The value stored on the row, before the ladder is applied. The lead
        # card's «Поручить» control needs it: an empty select there means
        # «делает владелец лида», and feeding it the resolved owner would turn
        # an implicit assignment into an explicit one on the next save.
        "explicit_assignee_user_id": activity.assignee_user_id,
        "author_user_id": activity.user_id,
        "author_name": author_name,
    }


def _tasks_query(workspace_id: uuid.UUID):
    """Базовый запрос по задачам рабочего пространства.

    LEFT JOIN на лид: с 0058 задача может жить без него. Пространство
    определяется либо лидом, либо собственным полем строки — ровно так,
    как это закреплено CHECK-ограничением в таблице.
    """
    from sqlalchemy import and_, or_, select
    from sqlalchemy.orm import aliased

    from app.leads.models import Lead

    assignee = aliased(User)
    owner = aliased(User)
    author = aliased(User)

    query = (
        select(Activity, Lead, assignee.name, owner.name, author.name)
        .outerjoin(Lead, Activity.lead_id == Lead.id)
        .outerjoin(assignee, Activity.assignee_user_id == assignee.id)
        .outerjoin(owner, Lead.assigned_to == owner.id)
        .outerjoin(author, Activity.user_id == author.id)
        .where(
            Activity.type == ActivityType.task.value,
            Activity.archived_at.is_(None),
            or_(
                Lead.workspace_id == workspace_id,
                Activity.workspace_id == workspace_id,
            ),
            # Задачи по лидам в корзине и в архиве в списках не нужны.
            or_(
                Activity.lead_id.is_(None),
                and_(Lead.archived_at.is_(None), Lead.deleted_at.is_(None)),
            ),
        )
    )
    return query, Lead


def _assigned_to_clause(Lead, user_id: uuid.UUID):
    """«Задача на этом человеке»: явный исполнитель, либо — если его нет —
    владелец лида, либо автор, если лида или его владельца нет."""
    from sqlalchemy import and_, or_

    return or_(
        Activity.assignee_user_id == user_id,
        and_(Activity.assignee_user_id.is_(None), Lead.assigned_to == user_id),
        and_(
            Activity.assignee_user_id.is_(None),
            or_(Activity.lead_id.is_(None), Lead.assigned_to.is_(None)),
            Activity.user_id == user_id,
        ),
    )


# ---------------------------------------------------------------------------
# Task lists (audit G5 / DEBT: a live task must not fall off a list just
# because 200 or 500 other rows were created before it).
#
# ONE ordering for every task list, applied in the database:
#
#     task_done ASC, task_due_at ASC NULLS LAST, id DESC
#
# `task_done` first is the whole point: before G5 the order started at
# task_due_at, so 500 completed tasks with earlier deadlines filled the entire
# budget and the one thing left to do was never sent. Open work now always
# precedes finished work, whatever the dates.
#
# `id DESC` is not decoration. Two tasks routinely share a due date (a batch
# created by one automation, or a round hour typed by hand), and a keyset
# cursor over a non-unique key either skips rows or repeats them at every page
# boundary. The id makes the sort total.
#
# Pagination is keyset (cursor), not page/page_size. The project uses
# page/page_size for leads, where the sort key is stable; a task list is sorted
# by exactly the two columns the user mutates while reading it, so OFFSET would
# shift rows across the boundary the moment somebody ticks a checkbox — the
# page-two row that moves to page one is never seen. Counts, which is what
# `total` would have bought us, are returned separately and are computed over
# the whole server-side selection.
# ---------------------------------------------------------------------------

MAX_TASK_PAGE = 200


def _task_order_by():
    return (
        Activity.task_done.asc(),
        Activity.task_due_at.asc().nulls_last(),
        Activity.id.desc(),
    )


def encode_task_cursor(row: dict) -> str:
    """'<0|1>|<due iso or empty>|<uuid>' — the full sort key of a row."""
    due = row["task_due_at"]
    return f"{int(bool(row['task_done']))}|{due.isoformat() if due else ''}|{row['id']}"


def decode_task_cursor(cursor: str) -> tuple[bool, datetime | None, uuid.UUID]:
    done_s, due_s, id_s = cursor.split("|", 2)
    return bool(int(done_s)), (datetime.fromisoformat(due_s) if due_s else None), uuid.UUID(id_s)


class TaskCursorInvalid(Exception):
    """400 — the cursor is not one this endpoint issued."""


def _after_task_cursor(cursor: str):
    """Rows strictly after the cursor under the ordering above."""
    from sqlalchemy import and_, or_

    try:
        done, due, ident = decode_task_cursor(cursor)
    except (ValueError, AttributeError) as exc:
        raise TaskCursorInvalid(cursor) from exc

    if due is None:
        # NULLS LAST: inside this done-bucket nothing sorts after a NULL due
        # date except a smaller id.
        same_bucket = and_(
            Activity.task_done.is_(done),
            Activity.task_due_at.is_(None),
            Activity.id < ident,
        )
    else:
        same_bucket = and_(
            Activity.task_done.is_(done),
            or_(
                Activity.task_due_at > due,
                Activity.task_due_at.is_(None),
                and_(Activity.task_due_at == due, Activity.id < ident),
            ),
        )
    if done:
        # The done bucket is the last one; there is nothing beyond it.
        return same_bucket
    return or_(Activity.task_done.is_(True), same_bucket)


def _apply_status(query, status: str):
    """open / done / overdue, in SQL — never after the limit."""
    if status == "open":
        return query.where(Activity.task_done.is_(False))
    if status == "done":
        return query.where(Activity.task_done.is_(True))
    if status == "overdue":
        return query.where(
            Activity.task_done.is_(False),
            Activity.task_due_at.isnot(None),
            Activity.task_due_at < datetime.now(timezone.utc),
        )
    return query


async def _task_counts(db: AsyncSession, scoped) -> dict:
    """open / done / overdue / total over the WHOLE server-side selection.

    The screens show these numbers next to their filter chips and in the
    «N из M выполнено» progress bar. Counting the loaded page instead would
    make the number shrink as the user scrolls — and with pagination it would
    simply be wrong.
    """
    from sqlalchemy import and_, func

    now = datetime.now(timezone.utc)
    counts_q = scoped.with_only_columns(
        func.count().label("total"),
        func.count().filter(Activity.task_done.is_(False)).label("open"),
        func.count().filter(Activity.task_done.is_(True)).label("done"),
        func.count()
        .filter(
            and_(
                Activity.task_done.is_(False),
                Activity.task_due_at.isnot(None),
                Activity.task_due_at < now,
            )
        )
        .label("overdue"),
        maintain_column_froms=True,
    ).order_by(None)
    row = (await db.execute(counts_q)).one()
    return {"total": row.total, "open": row.open, "done": row.done, "overdue": row.overdue}


async def _page(
    db: AsyncSession, scoped, *, status: str, cursor: str | None, limit: int
) -> tuple[list[dict], str | None, dict]:
    """Count the scoped set, then fetch one ordered page of it."""
    limit = max(1, min(limit, MAX_TASK_PAGE))
    # Counted BEFORE the status filter: the screens label their open / done /
    # overdue chips with these numbers, so each chip has to know its own size
    # while a different one is selected.
    counts = await _task_counts(db, scoped)

    query = _apply_status(scoped, status)
    if cursor:
        query = query.where(_after_task_cursor(cursor))

    # limit + 1: one extra row answers "is there a next page" without a
    # second count, and is dropped before the response is built.
    rows = (
        await db.execute(query.order_by(*_task_order_by()).limit(limit + 1))
    ).all()
    items = [_task_row_to_dict(*row) for row in rows[:limit]]
    next_cursor = encode_task_cursor(items[-1]) if len(rows) > limit and items else None
    return items, next_cursor, counts


async def list_my_tasks(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str = "all",
    cursor: str | None = None,
    limit: int = 100,
) -> tuple[list[dict], str | None, dict]:
    """Задачи, которые числятся за этим человеком. Без AI — только то,
    что завели руками. Открытые идут первыми, потом по сроку."""
    query, Lead = _tasks_query(workspace_id)
    return await _page(
        db,
        query.where(_assigned_to_clause(Lead, user_id)),
        status=status,
        cursor=cursor,
        limit=limit,
    )


async def get_task_out(
    db: AsyncSession, *, workspace_id: uuid.UUID, task_id: uuid.UUID
) -> dict | None:
    """Одна задача в том же виде, что и строки списков — чтобы ответы
    на создание и правку не расходились по форме со списком."""
    query, _ = _tasks_query(workspace_id)
    row = (
        await db.execute(query.where(Activity.id == task_id))
    ).first()
    return _task_row_to_dict(*row) if row is not None else None


async def list_lead_tasks(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    status: str = "all",
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], str | None, dict]:
    """Все задачи одного лида — то, что показывает вкладка «Задачи» в карточке.

    Не сужается до задач читателя: кто может открыть карточку, тот видит всю
    работу по этому лиду. Доступ к самому лиду проверяет вызывающая сторона
    (`_get_lead_or_raise` плюс страж на роутере `/leads`).
    """
    query, _ = _tasks_query(workspace_id)
    return await _page(
        db,
        query.where(Activity.lead_id == lead_id),
        status=status,
        cursor=cursor,
        limit=limit,
    )


async def list_tasks(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor: User,
    assignee_user_id: uuid.UUID | None = None,
    author_user_id: uuid.UUID | None = None,
    status: str = "all",
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], str | None, dict]:
    """Список задач для страницы «Задачи».

    Менеджер видит только свои — фильтр по чужому исполнителю ему просто
    не даётся, а не отдаёт пустой список: так в интерфейсе нет вкладки,
    которая молча ничего не показывает. Руководитель и админ видят всех.
    """
    from sqlalchemy import or_

    query, Lead = _tasks_query(workspace_id)

    if actor.role in ("admin", "head"):
        if assignee_user_id is not None:
            query = query.where(_assigned_to_clause(Lead, assignee_user_id))
        if author_user_id is not None:
            query = query.where(Activity.user_id == author_user_id)
    else:
        # Менеджеру доступны задачи на нём и поставленные им самим.
        query = query.where(
            or_(_assigned_to_clause(Lead, actor.id), Activity.user_id == actor.id)
        )
        if author_user_id is not None:
            query = query.where(Activity.user_id == author_user_id)
        if assignee_user_id is not None:
            query = query.where(_assigned_to_clause(Lead, actor.id))

    return await _page(db, query, status=status, cursor=cursor, limit=limit)


class TaskAssigneeInvalid(Exception):
    """400 — исполнителя нет в этом рабочем пространстве."""


async def _resolve_assignee(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor: User,
    assignee_user_id: uuid.UUID | None,
):
    """Проверить исполнителя. Ставить задачу другому человеку может
    только руководитель или админ — менеджер заводит задачи себе."""
    if assignee_user_id is None or assignee_user_id == actor.id:
        return assignee_user_id
    if actor.role not in ("admin", "head"):
        raise ActivityForbidden(assignee_user_id)

    from sqlalchemy import select

    target = (
        await db.execute(
            select(User).where(
                User.id == assignee_user_id, User.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise TaskAssigneeInvalid(assignee_user_id)
    return assignee_user_id


async def _notify_assignee(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor: User,
    assignee_user_id: uuid.UUID | None,
    text: str,
    lead_id: uuid.UUID | None,
) -> None:
    """Сказать человеку, что на него повесили задачу. Себе не пишем."""
    if assignee_user_id is None or assignee_user_id == actor.id:
        return

    from app.notifications.services import safe_notify

    await safe_notify(
        db,
        workspace_id=workspace_id,
        user_id=assignee_user_id,
        kind="task_assigned",
        title="Вам поставили задачу",
        body=text[:400],
        lead_id=lead_id,
    )


async def create_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    actor: User,
    *,
    text: str,
    task_due_at: datetime | None,
    assignee_user_id: uuid.UUID | None,
    lead_id: uuid.UUID | None,
) -> Activity:
    """Создать задачу — с лидом или без. Вызывающий коммитит.

    Формат строки тот же, что у задач из карточки лида (body + title в
    payload_json), чтобы оба источника читались одним кодом.
    """
    # Менеджер без явного исполнителя ставит задачу себе — иначе на
    # чужом лиде она уедет владельцу карточки в обход правила «ставить
    # другим может только руководитель» (см. _resolve_assignee).
    if actor.role == "manager" and assignee_user_id is None:
        assignee_user_id = actor.id

    assignee_user_id = await _resolve_assignee(
        db, workspace_id=workspace_id, actor=actor, assignee_user_id=assignee_user_id
    )
    if lead_id is not None:
        lead = await _get_lead_or_raise(db, lead_id, workspace_id)
        if lead.deleted_at is not None:
            raise LeadNotFound(lead_id)

    activity = Activity(
        lead_id=lead_id,
        # Пространство пишем только у задач без лида — у остальных его
        # даёт сам лид (см. CHECK ck_activities_scope).
        workspace_id=None if lead_id is not None else workspace_id,
        user_id=actor.id,
        assignee_user_id=assignee_user_id,
        type=ActivityType.task.value,
        payload_json={"title": text, "source": "tasks_page"},
        body=text,
        task_due_at=task_due_at,
    )
    db.add(activity)
    await db.flush()
    await db.refresh(activity)

    await _notify_assignee(
        db,
        workspace_id=workspace_id,
        actor=actor,
        assignee_user_id=assignee_user_id,
        text=text,
        lead_id=lead_id,
    )
    return activity


async def load_task_for_actor(
    db: AsyncSession, workspace_id: uuid.UUID, task_id: uuid.UUID, actor: User
) -> tuple[Activity, object | None]:
    """Найти задачу по её id (без привязки к маршруту лида) и проверить
    права. Возвращает (задача, лид или None)."""
    from sqlalchemy import select

    activity = (
        await db.execute(select(Activity).where(Activity.id == task_id))
    ).scalar_one_or_none()
    if activity is None:
        raise ActivityNotFound(task_id)

    lead = None
    if activity.lead_id is not None:
        lead = await leads_repo.get_by_id(db, activity.lead_id, workspace_id)
        if lead is None:
            # Задача из чужого пространства — отвечаем «нет такой».
            raise ActivityNotFound(task_id)
    elif activity.workspace_id != workspace_id:
        raise ActivityNotFound(task_id)

    _authorize_task_actor(activity, actor, lead)
    if activity.type != ActivityType.task.value:
        raise ActivityWrongType("Not a task")
    return activity, lead


async def set_task_done_by_id(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    actor: User,
    *,
    done: bool,
) -> Activity:
    activity, _ = await load_task_for_actor(db, workspace_id, task_id, actor)
    if done:
        if activity.task_done:
            return activity
        return await repo.mark_task_done(db, activity, datetime.now(timezone.utc))
    if not activity.task_done:
        return activity
    return await repo.mark_task_open(db, activity)


async def update_task_by_id(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    actor: User,
    *,
    text: str | None,
    task_due_at: datetime | None,
    assignee_user_id: uuid.UUID | None,
    clear_due: bool = False,
    assignee_provided: bool = False,
) -> Activity:
    """Правка задачи по её id. Смена исполнителя шлёт ему уведомление.

    У `assignee_user_id` три состояния, и раньше различались только два:
    `None` означало одновременно «поле не прислали» и «снять исполнителя»,
    поэтому запрос с одним лишь сбросом отвергался как «нечего менять», а
    сброс вместе с новым текстом молча сохранял прежнего исполнителя
    (BUG-02). Факт наличия поля приходит отдельным флагом от роутера, как
    это уже сделано для срока через `clear_due`.
    """
    clear_assignee = assignee_provided and assignee_user_id is None
    if (
        text is None
        and task_due_at is None
        and assignee_user_id is None
        and not clear_due
        and not clear_assignee
    ):
        raise ValueError("нечего менять")

    if text is not None:
        text = text.strip()
        if not text:
            raise ValueError("текст задачи не может быть пустым")

    activity, lead = await load_task_for_actor(db, workspace_id, task_id, actor)

    if text is not None:
        activity.body = text
        activity.payload_json = {**(activity.payload_json or {}), "title": text}
    if clear_due:
        activity.task_due_at = None
    elif task_due_at is not None:
        activity.task_due_at = task_due_at
    if clear_assignee:
        # Снятие явного исполнителя возвращает задачу владельцу лида, а у
        # задачи без лида — автору (см. effective_assignee_id). На лиде это
        # значит «передать другому человеку», поэтому право то же, что и у
        # обычного назначения: только руководитель или админ. Иначе `null`
        # стал бы для менеджера обходным путём делегирования.
        if actor.role not in ("admin", "head"):
            raise ActivityForbidden(None)
        previous_effective = effective_assignee_id(activity, lead)
        activity.assignee_user_id = None
        new_effective = effective_assignee_id(activity, lead)
        # Уведомляем только если работа действительно сменила хозяина.
        if new_effective != previous_effective:
            await _notify_assignee(
                db,
                workspace_id=workspace_id,
                actor=actor,
                assignee_user_id=new_effective,
                text=activity.body or "Задача",
                lead_id=activity.lead_id,
            )
    elif assignee_user_id is not None and assignee_user_id != activity.assignee_user_id:
        activity.assignee_user_id = await _resolve_assignee(
            db,
            workspace_id=workspace_id,
            actor=actor,
            assignee_user_id=assignee_user_id,
        )
        await _notify_assignee(
            db,
            workspace_id=workspace_id,
            actor=actor,
            assignee_user_id=activity.assignee_user_id,
            text=activity.body or "Задача",
            lead_id=activity.lead_id,
        )

    await db.flush()
    await db.refresh(activity)
    return activity


async def _get_lead_or_raise(
    db: AsyncSession, lead_id: uuid.UUID, workspace_id: uuid.UUID
):
    """Возвращает лид — вызывающим он нужен, чтобы понять, кто им владеет
    (владелец лида = исполнитель задачи, у которой не задан явный)."""
    lead = await leads_repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)
    return lead


async def list_activities(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    *,
    type_filter: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Activity], str | None]:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    return await repo.list_for_lead(
        db, lead_id, type_filter=type_filter, cursor=cursor, limit=limit
    )


async def create_activity(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    actor: User,
    payload_dict: dict,
) -> Activity:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    _validate_type(payload_dict.get("type", ""))
    is_task = payload_dict.get("type") == ActivityType.task.value
    if is_task:
        # Срок необязателен. Он требовался только здесь, и та же задача,
        # заведённая через POST /tasks, сохранялась без срока — один и тот
        # же объект жил по разным правилам в зависимости от экрана
        # (BUG-03). Текст по-прежнему обязателен: необязательный срок не
        # означает необязательное всё.
        if not (payload_dict.get("body") or "").strip():
            raise ValueError("текст задачи не может быть пустым")

    # Та же поправка, что в create_task: менеджер без явного
    # исполнителя ставит задачу себе, а не владельцу чужого лида.
    if is_task and actor.role == "manager" and payload_dict.get("assignee_user_id") is None:
        payload_dict = {**payload_dict, "assignee_user_id": actor.id}

    assignee_user_id = payload_dict.get("assignee_user_id")
    if assignee_user_id is not None and not is_task:
        # Исполнитель осмыслен только у задачи; на комментарии и письма
        # его молча не вешаем.
        payload_dict = {**payload_dict, "assignee_user_id": None}
        assignee_user_id = None
    elif assignee_user_id is not None:
        await _resolve_assignee(
            db,
            workspace_id=workspace_id,
            actor=actor,
            assignee_user_id=assignee_user_id,
        )

    activity = await repo.create(db, lead_id, actor.id, payload_dict)
    if is_task:
        await _notify_assignee(
            db,
            workspace_id=workspace_id,
            actor=actor,
            assignee_user_id=assignee_user_id,
            text=(payload_dict.get("body") or "Задача"),
            lead_id=lead_id,
        )
    return activity


def effective_assignee_id(activity: Activity, lead=None) -> uuid.UUID | None:
    """Кто должен делать задачу.

    Явный исполнитель, иначе владелец лида (так задачи вели себя до
    появления поля — руководитель ставил задачу на карточку, и её видел
    тот, кому карточка принадлежит), иначе автор.
    """
    if activity.assignee_user_id is not None:
        return activity.assignee_user_id
    if lead is not None and lead.assigned_to is not None:
        return lead.assigned_to
    return activity.user_id


def _authorize_task_actor(activity: Activity, actor: User, lead=None) -> None:
    """Задачу может трогать автор, исполнитель или admin/head.

    Исполнитель добавлен вместе с полем `assignee_user_id`: до этого
    менеджер видел в своём списке задачу, поставленную руководителем на
    его лид, но закрыть её не мог — проверка пропускала только автора.

    Raise BEFORE inspecting the row's type so status codes don't leak existence.
    """
    if actor.role in ("admin", "head"):
        return
    if activity.user_id == actor.id:
        return
    if effective_assignee_id(activity, lead) == actor.id:
        return
    raise ActivityForbidden(activity.id)


async def update_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    actor: User,
    body: str | None,
    task_due_at: datetime | None,
    clear_due: bool = False,
) -> Activity:
    """Update body and/or task_due_at on a task-Activity. Raises
    LeadNotFound / ActivityNotFound / ActivityForbidden / ValueError if not a task."""
    if body is None and task_due_at is None and not clear_due:
        raise ValueError("at least one of body or task_due_at must be provided")
    lead = await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    _authorize_task_actor(activity, actor, lead)
    if activity.type != ActivityType.task.value:
        raise ValueError("only task activities can be updated via this endpoint")
    if body is not None:
        cleaned = body.strip()
        if not cleaned:
            raise ValueError("body cannot be empty")
        activity.body = cleaned
        if activity.payload_json is None:
            activity.payload_json = {}
        activity.payload_json = {**activity.payload_json, "title": cleaned}
    if clear_due:
        activity.task_due_at = None
    elif task_due_at is not None:
        activity.task_due_at = task_due_at
    await db.flush()
    await db.refresh(activity)
    return activity


async def update_comment(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    actor: User,
    body: str,
) -> Activity:
    """Edit the text of a manager comment. Only the comment's author or
    an admin may edit (mirrors the notes domain edit-own rule). Raises
    LeadNotFound / ActivityNotFound / ActivityForbidden / ValueError."""
    cleaned = body.strip()
    if not cleaned:
        raise ValueError("body cannot be empty")
    await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    # Authorize BEFORE inspecting the row's type/shape — otherwise the
    # 404/400/403 status code becomes a within-workspace oracle that lets
    # a non-owner enumerate the existence and type of other managers'
    # activities. A non-owner always gets a uniform 403.
    if activity.user_id != actor.id and actor.role != "admin":
        raise ActivityForbidden(activity_id)
    if activity.type != ActivityType.comment.value:
        raise ValueError("only comment activities can be edited")
    # ask-Blake questions are AI-conversation turns paired with an answer
    # row; editing the question after the fact would desync the visible
    # Q/A. Keep them immutable.
    if (activity.payload_json or {}).get("source") == "ask_blake":
        raise ValueError("ask-Blake questions cannot be edited")
    activity.body = cleaned
    # Explicit edited flag (JSON column → no migration) so the feed can
    # mark «изменено» exactly, instead of guessing from timestamp deltas.
    activity.payload_json = {**(activity.payload_json or {}), "edited": True}
    await db.flush()
    await db.refresh(activity)
    return activity


async def archive_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    actor: User,
) -> Activity:
    """Soft-archive a task-Activity. Sets archived_at = now() so the row is
    hidden from active views but preserved (with its file attachments) in the
    per-lead archive. File-attachment Activities are NOT cascade-archived;
    they remain visible under the archived task in the archive view.
    Raises LeadNotFound / ActivityNotFound / ActivityForbidden / ValueError."""
    lead = await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    _authorize_task_actor(activity, actor, lead)
    if activity.type != ActivityType.task.value:
        raise ValueError("only task activities can be archived via this endpoint")
    if activity.archived_at is not None:
        return activity  # already archived — no-op (idempotent)
    activity.archived_at = datetime.now(timezone.utc)
    return activity


async def restore_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    actor: User,
) -> Activity:
    """Restore an archived task. Sets archived_at = NULL.
    Raises LeadNotFound / ActivityNotFound / ActivityForbidden / ValueError."""
    lead = await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    _authorize_task_actor(activity, actor, lead)
    if activity.type != ActivityType.task.value:
        raise ValueError("only task activities can be restored via this endpoint")
    activity.archived_at = None
    return activity


async def complete_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    actor: User,
) -> Activity:
    """Raises LeadNotFound / ActivityNotFound / ActivityForbidden / ActivityWrongType."""
    lead = await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    _authorize_task_actor(activity, actor, lead)
    if activity.type != ActivityType.task.value:
        raise ActivityWrongType("Cannot complete non-task activity")
    if activity.task_done:
        return activity  # idempotent
    return await repo.mark_task_done(db, activity, datetime.now(timezone.utc))


async def reopen_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    actor: User,
) -> Activity:
    """Reopen a completed task so it returns to the active list.
    Raises LeadNotFound / ActivityNotFound / ActivityForbidden / ActivityWrongType."""
    lead = await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    _authorize_task_actor(activity, actor, lead)
    if activity.type != ActivityType.task.value:
        raise ActivityWrongType("Cannot reopen non-task activity")
    if not activity.task_done:
        return activity  # idempotent
    return await repo.mark_task_open(db, activity)


# Author-name resolution for the unified feed. Anything written by the
# AI runner / chat handler is presented as «Блейк» regardless of the
# user_id stamped on the row (some chat answers carry the asking
# manager's id for audit; the visible author is still the AI).
_AI_AUTHOR_NAME = "Блейк"
_AI_TYPES = {ActivityType.ai_suggestion.value}


def _resolve_author_name(activity: Activity, joined_name: str | None) -> str | None:
    if activity.type in _AI_TYPES:
        return _AI_AUTHOR_NAME
    return joined_name


async def list_feed(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[tuple[Activity, str | None]], str | None]:
    """Lists feed items (no type filter — the unified feed shows
    everything) and resolves `author_name` per row via the AI override
    rule defined above."""
    await _get_lead_or_raise(db, lead_id, workspace_id)
    rows, next_cursor = await repo.list_feed_for_lead(
        db, lead_id, cursor=cursor, limit=limit
    )
    resolved: list[tuple[Activity, str | None]] = [
        (act, _resolve_author_name(act, name)) for (act, name) in rows
    ]
    return resolved, next_cursor
