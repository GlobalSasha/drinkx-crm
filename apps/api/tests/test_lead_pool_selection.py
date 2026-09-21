"""Сервер — единственный источник истины для выборки базы лидов (аудит G6).

До G6 `/leads-pool` брал одну страницу до 500 карточек и решал в браузере,
какие из них подходят под фильтры. Карточка за этой границей не находилась
ни поиском, ни фильтром; счётчики описывали загруженный кусок; экспорт и
«Выдать по фильтру» работали каждый по своему, более узкому набору условий.

Воспроизведение — в `repro_g6_lead_pool.py`, прогоняется на базовом коммите.

Здесь закреплено то, что должно держаться: один контракт выборки на список,
счётчики, экспорт и выдачу; отбор и порядок в базе; счётчики по всей
выборке; ограничения по рабочему пространству и роли не ослаблены.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE
from tests.lead_pool_dataset import (
    POOL_SIZE,
    TARGET_CITY,
    TARGET_EMAIL,
    TARGET_INN,
    TARGET_NAME,
    TARGET_PHONE,
    TARGET_PRIORITY,
    TARGET_SEGMENT,
    TARGET_SOURCE,
    TARGET_TAGS,
    seed_pool,
)

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


# --- хелперы ---------------------------------------------------------------

async def _user(db, workspace_id, role: str, name: str):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


def sel(**kwargs):
    from app.leads.selection import LeadSelection

    return LeadSelection.pool(**kwargs)


async def ids_of(db, workspace_id, selection):
    from app.leads import repositories as repo

    return await repo.list_selection_ids(db, workspace_id, selection)


async def page_of(db, workspace_id, selection, *, page=1, page_size=50):
    from app.leads import repositories as repo

    return await repo.list_pool(
        db, workspace_id, selection, page=page, page_size=page_size
    )


async def call(db, actor, method: str, path: str, **kwargs):
    """Настоящий HTTP-запрос: подменяются только сессия и пользователь."""
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1–2. Историческая граница
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_search_finds_a_lead_far_beyond_the_old_500_boundary(db, workspace):
    target_id, _ = await seed_pool(db, workspace.id)

    found = await ids_of(db, workspace.id, sel(q=TARGET_NAME))
    assert found == [target_id]

    # И на первой же странице: выборка сузилась в базе, а не в браузере.
    items, total = await page_of(db, workspace.id, sel(q=TARGET_NAME), page_size=50)
    assert total == 1
    assert [lead.id for lead in items] == [target_id]


@skip_no_pg
@pytest.mark.asyncio
async def test_a_previously_client_only_filter_finds_the_same_lead(db, workspace):
    """Приоритет и tier применялись только в браузере."""
    target_id, _ = await seed_pool(db, workspace.id)

    assert await ids_of(db, workspace.id, sel(priorities=["A"])) == [target_id]
    assert await ids_of(db, workspace.id, sel(tiers=["A"])) == [target_id]
    assert await ids_of(db, workspace.id, sel(deal_types=["station"])) == [target_id]
    assert await ids_of(db, workspace.id, sel(sources=[TARGET_SOURCE])) == [target_id]


# ---------------------------------------------------------------------------
# 3–5. Булева логика
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_multiple_values_inside_one_facet_are_or(db, workspace):
    await seed_pool(db, workspace.id)

    moscow = set(await ids_of(db, workspace.id, sel(cities=["Москва"])))
    kazan = set(await ids_of(db, workspace.id, sel(cities=[TARGET_CITY])))
    both = set(await ids_of(db, workspace.id, sel(cities=["Москва", TARGET_CITY])))

    assert moscow and kazan
    assert both == moscow | kazan


@skip_no_pg
@pytest.mark.asyncio
async def test_different_facets_are_and(db, workspace):
    target_id, _ = await seed_pool(db, workspace.id)

    by_city = set(await ids_of(db, workspace.id, sel(cities=[TARGET_CITY])))
    by_priority = set(await ids_of(db, workspace.id, sel(priorities=["A"])))
    both = set(
        await ids_of(db, workspace.id, sel(cities=[TARGET_CITY], priorities=["A"]))
    )

    assert both == by_city & by_priority == {target_id}
    assert len(by_city) > 1, "фильтр по городу обязан отбирать не одну строку"


@skip_no_pg
@pytest.mark.asyncio
async def test_tags_are_and_not_or(db, workspace):
    """Семантика интерфейса: карточка обязана нести каждый выбранный тег."""
    await seed_pool(db, workspace.id)

    vip = set(await ids_of(db, workspace.id, sel(tags=["vip"])))
    y2026 = set(await ids_of(db, workspace.id, sel(tags=["2026"])))
    both = set(await ids_of(db, workspace.id, sel(tags=["vip", "2026"])))

    assert vip and y2026
    assert both == vip & y2026
    assert len(both) < len(vip | y2026), "ИЛИ по тегам дало бы больше"


# ---------------------------------------------------------------------------
# 6–9. Значения фильтров
# ---------------------------------------------------------------------------


def test_tier_thresholds_at_every_boundary():
    """Пороги перенесены на сервер без изменений."""
    from app.leads.selection import tier_for_score

    cases = {
        200: "A", 100: "A", 81: "A", 80: "A",
        79: "B", 61: "B", 60: "B",
        59: "C", 41: "C", 40: "C",
        39: "D", 1: "D", 0: "D", None: "D",
    }
    for score, expected in cases.items():
        assert tier_for_score(score) == expected, score


@skip_no_pg
@pytest.mark.asyncio
async def test_tier_ranges_partition_the_pool(db, workspace):
    """Каждая карточка ровно в одном tier, и сумма сходится с пулом."""
    await seed_pool(db, workspace.id)

    buckets = {}
    for tier in ("A", "B", "C", "D"):
        buckets[tier] = set(await ids_of(db, workspace.id, sel(tiers=[tier])))

    all_ids = set(await ids_of(db, workspace.id, sel()))
    union: set = set()
    for tier, ids in buckets.items():
        assert not (union & ids), f"{tier} пересекается с другим tier"
        union |= ids
    assert union == all_ids
    assert len(all_ids) == POOL_SIZE


@skip_no_pg
@pytest.mark.asyncio
async def test_fit_min(db, workspace):
    from sqlalchemy import select

    from app.leads.models import Lead

    await seed_pool(db, workspace.id)
    ids = await ids_of(db, workspace.id, sel(fit_min=90))
    rows = (
        await db.execute(select(Lead.fit_score).where(Lead.id.in_(ids)))
    ).scalars().all()
    assert rows and all(float(v) >= 90 for v in rows)

    expected = (
        await db.execute(
            select(Lead.id).where(
                Lead.workspace_id == workspace.id, Lead.fit_score >= 90
            )
        )
    ).scalars().all()
    assert set(ids) == set(expected)


@skip_no_pg
@pytest.mark.asyncio
async def test_has_email_and_has_phone(db, workspace):
    from sqlalchemy import select

    from app.leads.models import Lead

    await seed_pool(db, workspace.id)

    with_email = await ids_of(db, workspace.id, sel(has_email=True))
    with_phone = await ids_of(db, workspace.id, sel(has_phone=True))
    both = await ids_of(db, workspace.id, sel(has_email=True, has_phone=True))

    real_email = set(
        (
            await db.execute(
                select(Lead.id).where(
                    Lead.workspace_id == workspace.id, Lead.email.isnot(None)
                )
            )
        ).scalars()
    )
    assert set(with_email) == real_email
    assert set(both) == set(with_email) & set(with_phone)
    assert 0 < len(both) < len(with_email)


# ---------------------------------------------------------------------------
# 10–13. Текстовый поиск
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_search_by_name_email_inn_and_formatted_phone(db, workspace):
    target_id, _ = await seed_pool(db, workspace.id)

    # Название — подстрока без учёта регистра.
    assert target_id in await ids_of(db, workspace.id, sel(q="целевая кофейня"))
    # Почта — тоже подстрока и тоже без учёта регистра.
    assert await ids_of(db, workspace.id, sel(q=TARGET_EMAIL.lower())) == [target_id]
    assert await ids_of(db, workspace.id, sel(q="target.lead@")) == [target_id]
    # ИНН — подстрока.
    assert await ids_of(db, workspace.id, sel(q=TARGET_INN)) == [target_id]
    # Телефон: записан «+7 (495) 123-45-67», ищем как угодно.
    for typed in (TARGET_PHONE, "74951234567", "+7 495 123 45 67", "8 (495) 123-45-67"[1:]):
        found = await ids_of(db, workspace.id, sel(q=typed))
        assert target_id in found, typed


@skip_no_pg
@pytest.mark.asyncio
async def test_whitespace_only_query_is_no_search(db, workspace):
    await seed_pool(db, workspace.id)
    assert len(await ids_of(db, workspace.id, sel(q="   "))) == POOL_SIZE
    assert len(await ids_of(db, workspace.id, sel(q=""))) == POOL_SIZE


@skip_no_pg
@pytest.mark.asyncio
async def test_wildcards_in_the_query_are_literal(db, workspace):
    """`%` из строки поиска не должен означать «что угодно»."""
    from app.leads.models import Lead

    await seed_pool(db, workspace.id)
    db.add(
        Lead(
            workspace_id=workspace.id,
            company_name="Скидка%Кофе",
            assignment_status="pool",
        )
    )
    await db.flush()

    # Без цифр в запросе, чтобы не задеть поиск по телефону.
    assert len(await ids_of(db, workspace.id, sel(q="ка%Ко"))) == 1
    assert len(await ids_of(db, workspace.id, sel(q="%"))) == 1, (
        "иначе один символ вернул бы весь пул"
    )
    assert len(await ids_of(db, workspace.id, sel(q="_"))) == 0, (
        "подчёркивание — тоже обычный символ"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_a_short_digit_query_does_not_match_every_phone(db, workspace):
    """Прежнее правило: телефон ищется от трёх цифр."""
    await seed_pool(db, workspace.id)
    two_digits = await ids_of(db, workspace.id, sel(q="74"))
    by_phone = await ids_of(db, workspace.id, sel(has_phone=True))
    assert len(two_digits) < len(by_phone)


# ---------------------------------------------------------------------------
# 14–15. Область пула
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_form_id_and_needs_review_scope_the_pool(db, workspace):
    from app.forms.models import WebForm
    from app.leads.models import Lead

    await seed_pool(db, workspace.id, size=20)

    form = WebForm(
        workspace_id=workspace.id,
        name="Лендинг",
        slug=f"land-{uuid.uuid4().hex[:6]}",
        fields_json=[],
    )
    db.add(form)
    await db.flush()
    from_form = Lead(
        workspace_id=workspace.id,
        company_name="Из формы",
        assignment_status="pool",
        source=f"form:{form.slug}",
        needs_review=True,
    )
    db.add(from_form)
    await db.flush()

    assert await ids_of(db, workspace.id, sel(form_id=form.id)) == [from_form.id]
    assert await ids_of(db, workspace.id, sel(needs_review=True)) == [from_form.id]
    assert from_form.id not in await ids_of(db, workspace.id, sel(needs_review=False))
    # Неизвестная форма — пустая выборка, а не снятый фильтр.
    assert await ids_of(db, workspace.id, sel(form_id=uuid.uuid4())) == []


# ---------------------------------------------------------------------------
# 16–17. Страницы и счётчики
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_pagination_is_stable_when_sort_values_collide(db, workspace):
    """Пачка импорта: одинаковые fit_score и created_at у всех строк."""
    from app.leads.models import Lead

    same_time = datetime(2026, 5, 5, tzinfo=timezone.utc)
    for i in range(120):
        db.add(
            Lead(
                workspace_id=workspace.id,
                company_name=f"Одинаковая {i:03d}",
                assignment_status="pool",
                fit_score=50,
                created_at=same_time,
                updated_at=same_time,
            )
        )
    await db.flush()

    seen: list = []
    for page in range(1, 20):
        items, total = await page_of(db, workspace.id, sel(), page=page, page_size=7)
        if not items:
            break
        seen.extend(lead.id for lead in items)
    assert total == 120
    assert len(seen) == 120
    assert len(set(seen)) == 120, "границы страниц потеряли или повторили строки"
    assert seen == await ids_of(db, workspace.id, sel())


@skip_no_pg
@pytest.mark.asyncio
async def test_facet_counts_do_not_depend_on_the_page(db, workspace):
    from app.leads import repositories as repo

    await seed_pool(db, workspace.id)

    facets = await repo.pool_facets(db, workspace.id, sel())
    by_value = {f["value"]: f["count"] for f in facets["cities"]}
    assert sum(by_value.values()) == POOL_SIZE
    assert by_value[TARGET_CITY] == 40

    # Та же карточка присутствует ровно один раз в приоритетах и в tier.
    priorities = {f["value"]: f["count"] for f in facets["priorities"]}
    assert priorities[TARGET_PRIORITY] == 1
    tiers = {f["value"]: f["count"] for f in facets["tiers"]}
    assert tiers["A"] == 1
    assert sum(tiers.values()) == POOL_SIZE

    # Счётчики не зависят ни от страницы, ни от выбранных фасетов.
    narrowed = await repo.pool_facets(
        db, workspace.id, sel(cities=["Москва"], q="что угодно")
    )
    assert narrowed["cities"] == facets["cities"]

    tags = {f["value"]: f["count"] for f in facets["tags"]}
    assert set(TARGET_TAGS) <= set(tags)
    segments = {f["value"]: f["count"] for f in facets["segments"]}
    assert segments[TARGET_SEGMENT] == 1


# ---------------------------------------------------------------------------
# 18–19. Права и рабочее пространство
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_reach_the_pool_endpoints(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")
    await seed_pool(db, workspace.id, size=5)

    for path in ("/leads/pool", "/leads/pool/facets"):
        res = await call(db, manager, "GET", path)
        assert res.status_code == 403, path

    res = await call(
        db, manager, "POST", "/leads/assign",
        json={"to_user_id": str(manager.id), "mode": "filter", "limit": 1},
    )
    assert res.status_code == 403


@skip_no_pg
@pytest.mark.asyncio
async def test_the_pool_never_crosses_a_workspace(db, workspace):
    from app.auth.models import Workspace
    from app.forms.models import WebForm

    await seed_pool(db, workspace.id, size=30)

    other = Workspace(name="Other WS", plan="free")
    db.add(other)
    await db.flush()
    outsider = await _user(db, other.id, "admin", "Outsider")
    await seed_pool(db, other.id, size=10)

    # Чужая форма не расширяет выборку: она просто не находится.
    foreign_form = WebForm(
        workspace_id=workspace.id,
        name="Наша",
        slug=f"ours-{uuid.uuid4().hex[:6]}",
        fields_json=[],
    )
    db.add(foreign_form)
    await db.flush()
    assert await ids_of(db, other.id, sel(form_id=foreign_form.id)) == []

    mine = set(await ids_of(db, workspace.id, sel()))
    theirs = set(await ids_of(db, other.id, sel()))
    assert len(mine) == 30 and len(theirs) == 10
    assert not (mine & theirs)

    res = await call(db, outsider, "GET", "/leads/pool?page_size=200")
    assert res.status_code == 200
    assert res.json()["total"] == 10


# ---------------------------------------------------------------------------
# 20–22. Экспорт и выдача «по фильтру» — та же выборка
# ---------------------------------------------------------------------------


async def _export_ids(db, workspace_id, selection) -> set:
    """Прогоняет настоящую задачу экспорта и собирает выгруженные строки."""
    from app.import_export import exporters as exporters_mod
    from app.import_export import redis_bytes as redis_mod
    from app.import_export.models import ExportJob
    from app.scheduled import jobs as jobs_mod

    job = ExportJob(
        workspace_id=workspace_id,
        format="csv",
        status="pending",
        filters_json=selection.to_json(),
    )
    db.add(job)
    await db.flush()

    exported: list = []
    real_rows = exporters_mod.leads_to_rows

    def _recording(leads, **kwargs):
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

    exporters_mod.leads_to_rows = _recording
    orig_factory = jobs_mod._build_task_engine_and_factory
    jobs_mod._build_task_engine_and_factory = lambda: (_Engine(), lambda: _Holder())
    orig_store = redis_mod.store_export_bytes
    redis_mod.store_export_bytes = _fake_store
    try:
        result = await jobs_mod._run_export(job.id)
    finally:
        exporters_mod.leads_to_rows = real_rows
        jobs_mod._build_task_engine_and_factory = orig_factory
        redis_mod.store_export_bytes = orig_store
    assert "error" not in result, result
    return {lead.id for lead in exported}


@skip_no_pg
@pytest.mark.asyncio
async def test_export_returns_exactly_the_list_selection(db, workspace):
    """Сравниваются идентификаторы, а не количества."""
    await seed_pool(db, workspace.id)

    combos = [
        sel(cities=[TARGET_CITY, "Москва"], priorities=["A", "B"]),
        sel(segments=[TARGET_SEGMENT, "АЗС"], tiers=["A", "C"]),
        sel(tags=["vip", "2026"]),
        sel(q="Компания 09", has_email=True),
        sel(has_phone=True, sources=["import"]),
        sel(cities=[TARGET_CITY], priorities=["A"], tags=["vip"], q="Целевая"),
        sel(needs_review=False, fit_min=80),
    ]
    for selection in combos:
        listed = await ids_of(db, workspace.id, selection)
        exported = await _export_ids(db, workspace.id, selection)
        assert exported == set(listed), selection
        assert listed, f"комбинация {selection} обязана что-то отбирать"


@skip_no_pg
@pytest.mark.asyncio
async def test_export_is_not_capped_to_one_page(db, workspace):
    await seed_pool(db, workspace.id)
    exported = await _export_ids(db, workspace.id, sel())
    assert len(exported) == POOL_SIZE

    page_items, _total = await page_of(db, workspace.id, sel(), page_size=50)
    assert len(page_items) == 50


@skip_no_pg
@pytest.mark.asyncio
async def test_export_does_not_include_trashed_leads(db, workspace):
    """Прежняя сборка фильтра не исключала удалённые карточки."""
    from app.leads.models import Lead

    await seed_pool(db, workspace.id, size=10)
    trashed = Lead(
        workspace_id=workspace.id,
        company_name="В корзине",
        assignment_status="pool",
        deleted_at=datetime.now(timezone.utc),
    )
    db.add(trashed)
    await db.flush()

    exported = await _export_ids(db, workspace.id, sel())
    assert trashed.id not in exported
    assert set(await ids_of(db, workspace.id, sel())) == exported


@skip_no_pg
@pytest.mark.asyncio
async def test_assign_by_filter_uses_the_same_selection(db, workspace):
    from app.leads import repositories as repo

    await seed_pool(db, workspace.id)
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")

    selection = sel(cities=[TARGET_CITY], tiers=["C"])
    screen = set(await ids_of(db, workspace.id, selection))
    assert len(screen) > 5

    n = 5
    # Порядок фиксируем ДО выдачи: выданные карточки уходят из пула, и
    # повторный запрос вернёт уже другое.
    expected_order = (await ids_of(db, workspace.id, selection))[:n]

    assigned = await repo.assign_pool_by_filter(
        db, workspace.id, manager.id, selection, limit=n
    )
    assigned_ids = {lead.id for lead in assigned}

    assert len(assigned_ids) == n
    assert assigned_ids <= screen, "выдали то, чего на экране нет"
    assert all(lead.assigned_to == manager.id for lead in assigned)
    assert all(lead.assignment_status == "assigned" for lead in assigned)
    # Порядок выдачи — тот же, что у списка: первые N.
    assert [lead.id for lead in assigned] == expected_order
    # И выданное действительно ушло из пула.
    assert not (set(await ids_of(db, workspace.id, selection)) & assigned_ids)

    _ = head


@skip_no_pg
@pytest.mark.asyncio
async def test_assign_by_filter_over_http_respects_every_filter(db, workspace):
    await seed_pool(db, workspace.id)
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")

    selection = sel(cities=[TARGET_CITY], priorities=["A"])
    screen = set(await ids_of(db, workspace.id, selection))
    assert len(screen) == 1

    res = await call(
        db, head, "POST", "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "filter",
            "city": None,
            "cities": [TARGET_CITY],
            "priorities": ["A"],
            "limit": 10,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["assigned_count"] == 1, body
    assert set(body["assigned_ids"]) == {str(i) for i in screen} if "assigned_ids" in body else True


@skip_no_pg
@pytest.mark.asyncio
async def test_assign_by_filter_keeps_skip_locked_and_the_pool_recheck(db, workspace):
    """Гонка: карточку забрали между выбором кандидатов и обновлением."""
    import inspect

    from app.leads import repositories as repo

    source = inspect.getsource(repo.assign_pool_by_filter)
    assert "skip_locked=True" in source, "SKIP LOCKED не должен исчезнуть"
    assert 'Lead.assignment_status == "pool"' in source, (
        "повторная проверка статуса при обновлении обязана остаться"
    )

    await seed_pool(db, workspace.id, size=20)
    manager = await _user(db, workspace.id, "manager", "Manager")

    # Половину пула забирает «кто-то другой» до выдачи.
    all_ids = await ids_of(db, workspace.id, sel())
    from sqlalchemy import update

    from app.leads.models import Lead

    await db.execute(
        update(Lead)
        .where(Lead.id.in_(all_ids[:10]))
        .values(assignment_status="assigned", assigned_to=manager.id)
    )
    await db.flush()

    assigned = await repo.assign_pool_by_filter(
        db, workspace.id, manager.id, sel(), limit=20
    )
    assert {lead.id for lead in assigned} == set(all_ids[10:])
