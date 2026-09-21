"""Воспроизведение дефектов G6: сервер не был источником истины для пула.

Не называется test_*: файл утверждает поведение ДО правки. Прогоняется на
базовом коммите:

    REQUIRE_TEST_DB=1 python -m pytest tests/repro_g6_lead_pool.py -q -s

A. Поиск за границей первой страницы. `/leads-pool` брал одну страницу до
   500 карточек и фильтровал их в браузере. У эндпоинта нет параметра `q`
   вообще, поэтому найти карточку, не попавшую в эти 500, было нечем.

B. Фильтр, который применялся только в браузере (приоритет, tier, тип
   сделки, источник, теги, наличие почты или телефона). Единственная
   подходящая карточка лежит за границей — экран показывает ноль.

C. Экспорт. `ExportPopover` на пуле отправлял урезанный набор полей, а
   worker понимает лишь часть из них и ищет `q` только по названию.
   Множество выгруженных идентификаторов не совпадает с тем, что на экране.

D. «Выдать по фильтру». Кнопка отправляет не фильтр, а список
   идентификаторов, собранный из уже загруженной и отфильтрованной в
   браузере страницы.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE
from tests.lead_pool_dataset import (
    POOL_SIZE,
    TARGET_CITY,
    TARGET_NAME,
    TARGET_PRIORITY,
    seed_pool,
)

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

OLD_PAGE_SIZE = 500  # то, что фронтенд просил одним запросом


def _tier_from_score(score: int) -> str:
    """Копия `tierFromScore` из apps/web/lib/types.ts — до G6 порог жил
    только во фронтенде."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _client_side_filter(items, *, q="", priority=None, tier=None):
    """То, что делал браузер: фильтрация по уже загруженным строкам."""
    out = []
    for lead in items:
        if priority and lead.priority != priority:
            continue
        if tier and _tier_from_score(lead.score) != tier:
            continue
        if q:
            needle = q.lower()
            name = (lead.company_name or "").lower()
            email = (lead.email or "").lower()
            inn = (lead.inn or "").lower()
            digits = "".join(ch for ch in q if ch.isdigit())
            phone_digits = "".join(ch for ch in (lead.phone or "") if ch.isdigit())
            matched = (
                needle in name
                or (email and needle in email)
                or (inn and needle in inn)
                or (len(digits) >= 3 and phone_digits and digits in phone_digits)
            )
            if not matched:
                continue
        out.append(lead)
    return out


async def _first_page(db, workspace_id, **kwargs):
    """Один запрос до 500 карточек — то, что делал фронтенд."""
    import inspect

    from app.leads import repositories as repo

    if "selection" in inspect.signature(repo.list_pool).parameters:
        raise AssertionError(
            "дефект исправлен: list_pool принимает каноническое описание "
            "выборки, отбор и поиск идут в базе — воспроизведение больше не "
            "описывает текущий код (см. test_lead_pool_selection.py)"
        )
    return await repo.list_pool(
        db, workspace_id, page=1, page_size=OLD_PAGE_SIZE, **kwargs
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_A_search_cannot_reach_a_lead_past_the_first_page(db, workspace):
    from sqlalchemy import select

    from app.leads.models import Lead

    target_id, _all_ids = await seed_pool(db, workspace.id)

    items, total = await _first_page(db, workspace.id)
    loaded_ids = [lead.id for lead in items]

    print(f"\n[A] карточек в пуле       : {total}")
    print(f"[A] загружено одним запросом: {len(items)} (page_size={OLD_PAGE_SIZE})")
    print(f"[A] целевая среди загруженных: {target_id in loaded_ids}")

    # 3. Прямой запрос к базе: карточка в пуле есть.
    in_db = (
        await db.execute(
            select(Lead.id).where(
                Lead.id == target_id,
                Lead.assignment_status == "pool",
                Lead.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    print(f"[A] в базе, в пуле          : {in_db is not None}")

    # 2. Поиск в интерфейсе её не находит: фильтрация идёт по загруженным.
    found = _client_side_filter(items, q=TARGET_NAME)
    print(f"[A] найдено поиском в UI    : {len(found)}")

    assert total == POOL_SIZE
    assert len(items) == OLD_PAGE_SIZE
    assert in_db is not None, "карточка обязана существовать в пуле"
    assert target_id not in loaded_ids, "целевая карточка должна быть за границей"
    assert found == [], "до G6 поиск не мог её найти"

    # И у самого эндпоинта нечем искать: параметра `q` нет.
    import inspect

    assert "q" not in inspect.signature(
        __import__("app.leads.repositories", fromlist=["list_pool"]).list_pool
    ).parameters, "у list_pool нет текстового поиска — искать нечем"


@skip_no_pg
@pytest.mark.asyncio
async def test_B_a_client_only_filter_reports_no_match(db, workspace):
    """Приоритет и tier применялись только в браузере."""
    target_id, _ = await seed_pool(db, workspace.id)
    items, total = await _first_page(db, workspace.id)

    by_priority = _client_side_filter(items, priority=TARGET_PRIORITY)
    by_tier = _client_side_filter(items, tier="A")

    print(f"\n[B] приоритет «{TARGET_PRIORITY}» на экране: {len(by_priority)}")
    print(f"[B] tier «A» на экране          : {len(by_tier)}")
    print(f"[B] а в пуле на самом деле      : 1 (целевая {target_id})")

    assert by_priority == [], "экран показывает ноль подходящих"
    assert by_tier == [], "и по tier тоже ноль"
    assert total == POOL_SIZE


@skip_no_pg
@pytest.mark.asyncio
async def test_C_export_selection_differs_from_the_screen(db, workspace):
    """Сравниваются идентификаторы, а не количества."""
    from app.import_export import exporters as exporters_mod
    from app.import_export.models import ExportJob
    from app.scheduled import jobs as jobs_mod

    target_id, _ = await seed_pool(db, workspace.id)

    # То, что видно на экране: пул, суженный городом и приоритетом.
    # Фильтр по городу до G6 тоже был клиентским, поэтому повторяем его
    # поверх загруженной страницы — ровно как браузер.
    items, _total = await _first_page(db, workspace.id)
    on_screen = {
        lead.id
        for lead in items
        if lead.city == TARGET_CITY and lead.priority == TARGET_PRIORITY
    }

    # То, что уходит в экспорт: ExportPopover на пуле отправляет только
    # city (если выбран ровно один), segment, fit_min, q и
    # assignment_status. Ни приоритета, ни tier, ни тегов, ни телефона.
    export_filters = {
        "city": TARGET_CITY,
        "assignment_status": "pool",
    }

    job = ExportJob(
        workspace_id=workspace.id,
        format="csv",
        status="pending",
        filters_json=dict(export_filters),
    )
    db.add(job)
    await db.flush()

    exported: list = []
    real_rows = exporters_mod.leads_to_rows

    def _recording_rows(leads, **kwargs):
        exported.extend(leads)
        return real_rows(leads, **kwargs)

    class _Holder:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *exc):
            return False

    class _Engine:
        async def dispose(self_inner):
            return None

    async def _fake_store(job_id, payload):
        return f"export:{job_id}"

    exporters_mod.leads_to_rows = _recording_rows
    orig_factory = jobs_mod._build_task_engine_and_factory
    jobs_mod._build_task_engine_and_factory = lambda: (_Engine(), lambda: _Holder())
    from app.import_export import redis_bytes as redis_mod

    orig_store = redis_mod.store_export_bytes
    redis_mod.store_export_bytes = _fake_store
    try:
        await jobs_mod._run_export(job.id)
    finally:
        exporters_mod.leads_to_rows = real_rows
        jobs_mod._build_task_engine_and_factory = orig_factory
        redis_mod.store_export_bytes = orig_store

    exported_ids = {lead.id for lead in exported}

    print(f"\n[C] на экране (город+приоритет): {len(on_screen)}")
    print(f"[C] выгружено экспортом        : {len(exported_ids)}")
    print(f"[C] целевая на экране          : {target_id in on_screen}")
    print(f"[C] целевая в выгрузке         : {target_id in exported_ids}")
    print(f"[C] лишних в выгрузке          : {len(exported_ids - on_screen)}")

    assert exported_ids != on_screen, "наборы обязаны разойтись — это и есть дефект"
    assert target_id in exported_ids and target_id not in on_screen, (
        "экспорт отдаёт карточку, которой на экране нет вообще"
    )
    assert len(exported_ids) > len(on_screen), (
        "экспорт не знает про приоритет и тянет весь город целиком"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_D_assign_by_filter_sends_ids_from_the_loaded_page(db, workspace):
    """Кнопка «Выдать по фильтру» отправляет mode=ids со списком из
    загруженной страницы, а не фильтр. Серверный режим фильтра при этом
    существует, но знает только про города, сегмент и fit_min."""
    import inspect

    from app.leads import repositories as repo

    await seed_pool(db, workspace.id)
    items, _ = await _first_page(db, workspace.id)

    # То, что модалка называет «подходит под фильтр» — длина загруженной и
    # отфильтрованной в браузере страницы, а не размер выборки в базе.
    visible_ids = [lead.id for lead in items]
    print(f"\n[D] «сейчас под фильтр подходит»: {len(visible_ids)}")
    print(f"[D] на самом деле в пуле        : {POOL_SIZE}")
    assert len(visible_ids) == OLD_PAGE_SIZE < POOL_SIZE

    params = inspect.signature(repo.assign_pool_by_filter).parameters
    supported = {p for p in params if p not in ("db", "workspace_id", "to_user_id")}
    print(f"[D] серверный фильтр выдачи знает: {sorted(supported)}")
    for missing in ("priorities", "tiers", "tags", "q", "sources", "has_email"):
        assert missing not in supported, (
            f"{missing} не поддерживается серверным режимом выдачи"
        )
