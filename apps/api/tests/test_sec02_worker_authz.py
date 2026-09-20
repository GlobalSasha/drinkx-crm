"""SEC2-F1/F2/T1 — полномочия и учёт при фактической записи bulk-update.

Три дефекта, найденные при ревью SEC-02:

F1  Автор задания загружался один раз ДО цикла, а сессия живёт с
    `expire_on_commit=False`. Между двумя закоммиченными строками роль
    можно отозвать — worker продолжал работать по устаревшему объекту.
    Плюс ветка `lead_id is None` (создание) возвращала «можно» до всякой
    проверки автора: задание без действующего автора создавало карточки.

F2  Строка, отклонённая по доступу, увеличивала `processed` дважды:
    один раз в своей ветке, второй — в `finally`, который выполняется и
    после `continue`.

T1  Проверка «чужая карточка не изменилась» опиралась на изменение,
    которого worker не умеет применять (`city` через before/after), и
    потому ничего не доказывала.

Здесь всё проверяется настоящим прогоном `_run_bulk_update` на
одноразовой локальной базе. Очередь и внешние вызовы не участвуют:
worker их не трогает, а движок подменён на тестовую сессию.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE
from tests.test_sec01_lead_scoped_access import _lead, _user

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

MARKER = "security-test-marker"


def tag_change(value: str = MARKER) -> dict:
    """Изменение, которое worker действительно умеет применять.

    `tags` + `op: add` проходит через `_apply_tags_changes` и меняет
    строку в базе. Прежний тест слал `city` с `before`/`after`: таких
    полей `Change` не читает, и «ничего не изменилось» выполнялось само
    собой, независимо от прав.
    """
    return {"field": "tags", "op": "add", "value": [value]}


def update_item(lead_id, *, name="Компания", changes=None) -> dict:
    return {
        "action": "update",
        "company_name": name,
        "inn": None,
        "lead_id": str(lead_id),
        "changes": changes if changes is not None else [tag_change()],
        "error": None,
        "match_confidence": "exact_id",
    }


def create_item(name: str = "Новая из импорта") -> dict:
    return {
        "action": "create",
        "company_name": name,
        "inn": None,
        "lead_id": None,
        "changes": [tag_change()],
        "error": None,
        "match_confidence": "not_found",
    }


async def make_job(db, workspace_id, user_id, items: list[dict]):
    from app.import_export.models import ImportJob

    job = ImportJob(
        workspace_id=workspace_id,
        user_id=user_id,
        status="previewed",
        format="bulk_update_yaml",
        source_filename="обновление.yaml",
        upload_size_bytes=100,
        total_rows=len(items),
        diff_json={
            "type": "bulk_update",
            "items": items,
            "stats": {"to_update": len(items), "to_create": 0, "errors": 0},
        },
    )
    db.add(job)
    await db.flush()
    return job


async def run_worker(db, job_id, *, after_each=None):
    """Прогон настоящего worker на тестовой сессии.

    `after_each(n)` вызывается ПОСЛЕ применения n-й строки — то есть
    между строками, до проверки прав для следующей. Именно туда и
    приходится отзыв роли: хук перед применением сработал бы уже после
    проверки и ничего бы не доказал.
    """
    from app.import_export import diff_engine as de
    from app.scheduled import jobs as jobs_mod

    class _Holder:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *exc):
            return False

    class _Engine:
        async def dispose(self_inner):
            return None

    calls = {"n": 0}
    real_apply = de.apply_diff_item

    async def _hooked_apply(session, **kwargs):
        result = await real_apply(session, **kwargs)
        calls["n"] += 1
        if after_each is not None:
            await after_each(calls["n"])
        return result

    orig_factory = jobs_mod._build_task_engine_and_factory
    jobs_mod._build_task_engine_and_factory = lambda: (_Engine(), lambda: _Holder())
    de.apply_diff_item = _hooked_apply
    try:
        return await jobs_mod._run_bulk_update(job_id)
    finally:
        jobs_mod._build_task_engine_and_factory = orig_factory
        de.apply_diff_item = real_apply


async def tags_of(db, lead_id) -> list[str]:
    from sqlalchemy import select

    from app.leads.models import Lead

    return list(
        (
            await db.execute(select(Lead.tags_json).where(Lead.id == lead_id))
        ).scalar_one()
        or []
    )


async def demote(db, user_id, role: str = "manager") -> None:
    """Меняет роль в базе, не трогая уже загруженный объект.

    Через Core UPDATE: присвоение атрибута обновило бы тот самый
    экземпляр, который держит worker, и проверка потеряла бы смысл.
    """
    from sqlalchemy import update

    from app.auth.models import User

    await db.execute(update(User).where(User.id == user_id).values(role=role))
    await db.commit()


# ---------------------------------------------------------------------------
# T1 — изменение, которое действительно применяется
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_supported_change_really_writes_for_the_owner(db, workspace):
    """Положительный контроль: без него «не изменилось» ничего не значит."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    mine = await _lead(db, workspace.id, owner.id, "Моя компания")
    job = await make_job(db, workspace.id, owner.id, [update_item(mine.id)])

    await run_worker(db, job.id)

    assert MARKER in await tags_of(db, mine.id)
    await db.refresh(job)
    assert (job.succeeded, job.failed) == (1, 0)


@skip_no_pg
@pytest.mark.asyncio
async def test_the_same_change_is_refused_on_a_colleagues_lead(db, workspace):
    """Отрицательный контроль тем же изменением, что и положительный."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    theirs = await _lead(db, workspace.id, peer.id, "Компания коллеги")
    job = await make_job(db, workspace.id, owner.id, [update_item(theirs.id)])

    await run_worker(db, job.id)

    assert MARKER not in await tags_of(db, theirs.id)
    await db.refresh(job)
    assert (job.succeeded, job.failed) == (0, 1)


# ---------------------------------------------------------------------------
# F1 — актуальные права на границе каждой строки
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_role_revoked_between_rows_stops_the_next_one(db, workspace):
    """Роль отзывают после первой закоммиченной строки.

    Первая строка остаётся применённой — отменять её задним числом не
    требуется. Следующая чужая карточка получает отказ. И сразу
    положительный контроль: своя карточка после понижения всё ещё
    обновляется, то есть проверка сузила права, а не выключила запись.
    """
    head = await _user(db, workspace.id, "head", "Head")
    peer = await _user(db, workspace.id, "manager", "Peer")
    first = await _lead(db, workspace.id, peer.id, "Первая чужая")
    second = await _lead(db, workspace.id, peer.id, "Вторая чужая")
    own = await _lead(db, workspace.id, head.id, "Своя карточка")

    job = await make_job(
        db, workspace.id, head.id,
        [update_item(first.id), update_item(second.id), update_item(own.id)],
    )

    async def revoke_after_first(applied_count: int):
        if applied_count == 1:
            await demote(db, head.id, "manager")

    await run_worker(db, job.id, after_each=revoke_after_first)

    assert MARKER in await tags_of(db, first.id), "первая строка должна остаться применённой"
    assert MARKER not in await tags_of(db, second.id), "после отзыва роли — отказ"
    assert MARKER in await tags_of(db, own.id), "своя карточка обновляется и после понижения"

    await db.refresh(job)
    assert (job.succeeded, job.failed) == (2, 1)


@skip_no_pg
@pytest.mark.asyncio
async def test_a_job_without_a_living_author_creates_nothing(db, workspace):
    """Нет действующего автора — нет и создания карточки."""
    from sqlalchemy import func, select

    from app.leads.models import Lead

    before = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.workspace_id == workspace.id)
        )
    ).scalar_one()

    job = await make_job(db, workspace.id, None, [create_item()])
    await run_worker(db, job.id)

    after = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.workspace_id == workspace.id)
        )
    ).scalar_one()
    assert after == before, "карточка не должна была появиться"

    created = (
        await db.execute(
            select(Lead.id).where(Lead.company_name == "Новая из импорта")
        )
    ).scalar_one_or_none()
    assert created is None

    await db.refresh(job)
    assert (job.succeeded, job.failed) == (0, 1)


@skip_no_pg
@pytest.mark.asyncio
async def test_a_deleted_author_stops_updates_too(db, workspace):
    """Автора удалили после постановки задания."""
    from sqlalchemy import delete

    from app.auth.models import User

    owner = await _user(db, workspace.id, "manager", "Owner")
    mine = await _lead(db, workspace.id, owner.id, "Моя компания")
    job = await make_job(db, workspace.id, owner.id, [update_item(mine.id)])

    await db.execute(delete(User).where(User.id == owner.id))
    await db.commit()

    await run_worker(db, job.id)

    assert MARKER not in await tags_of(db, mine.id)
    await db.refresh(job)
    assert (job.succeeded, job.failed) == (0, 1)


@skip_no_pg
@pytest.mark.asyncio
async def test_the_owner_may_still_create(db, workspace):
    """Импорт менеджерам не запрещён: создание с живым автором работает."""
    from sqlalchemy import select

    from app.leads.models import Lead

    owner = await _user(db, workspace.id, "manager", "Owner")
    job = await make_job(db, workspace.id, owner.id, [create_item("Создана менеджером")])

    await run_worker(db, job.id)

    created = (
        await db.execute(
            select(Lead).where(Lead.company_name == "Создана менеджером")
        )
    ).scalar_one_or_none()
    assert created is not None
    assert MARKER in (created.tags_json or [])
    await db.refresh(job)
    assert (job.succeeded, job.failed) == (1, 0)


# ---------------------------------------------------------------------------
# F2 — одна строка учитывается один раз
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_counters_add_up_on_a_mixed_batch(db, workspace):
    """Успех, отказ по доступу и ошибка разбора в одном задании."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    mine = await _lead(db, workspace.id, owner.id, "Моя компания")
    theirs = await _lead(db, workspace.id, peer.id, "Компания коллеги")

    broken = update_item(uuid.uuid4(), name="Ненайденная")
    broken["error"] = "Лид не найден"
    broken["lead_id"] = None

    job = await make_job(
        db, workspace.id, owner.id,
        [update_item(mine.id), update_item(theirs.id), broken],
    )

    await run_worker(db, job.id)
    await db.refresh(job)

    assert job.succeeded == 1
    assert job.failed == 2
    assert job.processed == job.succeeded + job.failed == job.total_rows == 3


@skip_no_pg
@pytest.mark.asyncio
async def test_a_single_refused_row_is_counted_once(db, workspace):
    """Минимальный случай из ревью: одна запрещённая строка."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    theirs = await _lead(db, workspace.id, peer.id, "Компания коллеги")
    job = await make_job(db, workspace.id, owner.id, [update_item(theirs.id)])

    await run_worker(db, job.id)
    await db.refresh(job)

    assert (job.processed, job.failed, job.succeeded) == (1, 1, 0)
    assert job.processed == job.total_rows == 1


# ---------------------------------------------------------------------------
# T1 — сквозной путь: настоящий YAML → preview → apply → worker
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_end_to_end_yaml_preview_and_apply(db, workspace):
    """Как это работает у человека: файл, разбор, применение.

    Три способа сопоставления — по идентификатору, по ИНН и по названию, —
    каждый на своей карточке коллеги и на своей собственной. Чужие должны
    отсеяться на разборе, свои — реально измениться после применения.
    """
    import yaml as _yaml

    from app.import_export.adapters.bulk_update import parse_bulk_update
    from app.import_export.diff_engine import compute_diff, diff_to_jsonable

    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")

    mine_by_id = await _lead(db, workspace.id, owner.id, "Моя по идентификатору")
    mine_by_inn = await _lead(db, workspace.id, owner.id, "Моя по ИНН")
    mine_by_inn.inn = "7700000011"
    mine_by_name = await _lead(db, workspace.id, owner.id, "Моя по названию")

    theirs_by_id = await _lead(db, workspace.id, peer.id, "Чужая по идентификатору")
    theirs_by_inn = await _lead(db, workspace.id, peer.id, "Чужая по ИНН")
    theirs_by_inn.inn = "7700000022"
    theirs_by_name = await _lead(db, workspace.id, peer.id, "Чужая по названию")
    await db.flush()

    def row(match_by, company):
        return {
            "action": "update",
            "match_by": match_by,
            "company": company,
            "fields": {"tags": {"add": [MARKER]}},
        }

    payload = {
        "updates": [
            row("id", {"id": str(mine_by_id.id), "name": "Моя по идентификатору"}),
            row("inn", {"inn": "7700000011", "name": "Моя по ИНН"}),
            row("company_name", {"name": "Моя по названию"}),
            row("id", {"id": str(theirs_by_id.id), "name": "Чужая по идентификатору"}),
            row("inn", {"inn": "7700000022", "name": "Чужая по ИНН"}),
            row("company_name", {"name": "Чужая по названию"}),
        ]
    }
    content = _yaml.safe_dump(payload, allow_unicode=True).encode("utf-8")

    updates = parse_bulk_update(content)
    assert len(updates) == 6, updates

    diff = await compute_diff(
        db, workspace_id=workspace.id, updates=updates, actor=owner
    )
    resolved = [d for d in diff if d.error is None]
    refused = [d for d in diff if d.error is not None]
    assert len(resolved) == 3, [d.company_name for d in resolved]
    assert len(refused) == 3, [(d.company_name, d.error) for d in refused]
    assert all(d.error == "Лид не найден" for d in refused)
    assert all(d.lead_id is None for d in refused)

    job = await make_job(db, workspace.id, owner.id, diff_to_jsonable(diff))
    job.total_rows = len(diff)
    await db.flush()

    await run_worker(db, job.id)

    for lead in (mine_by_id, mine_by_inn, mine_by_name):
        assert MARKER in await tags_of(db, lead.id), lead.company_name
    for lead in (theirs_by_id, theirs_by_inn, theirs_by_name):
        assert MARKER not in await tags_of(db, lead.id), lead.company_name

    await db.refresh(job)
    assert job.succeeded == 3
    assert job.failed == 3
    assert job.processed == job.succeeded + job.failed == job.total_rows == 6
