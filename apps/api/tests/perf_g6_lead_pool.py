"""Замер выборки базы лидов на локальном наборе (аудит G6, §11).

Не тест: печатает числа для отчёта. Не называется test_*, чтобы не
попадать в обычный прогон.

    REQUIRE_TEST_DB=1 python -m pytest tests/perf_g6_lead_pool.py -q -s

Считает запросы и время для одного обращения к списку и к счётчикам на
наборе из 1200 карточек и показывает план основного запроса. Прод не
трогается: набор локальный, одноразовый.
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy import event, text

import app.main  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE
from tests.lead_pool_dataset import TARGET_CITY, seed_pool

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


class Counter:
    """Считает SQL-запросы, ушедшие в базу за блок кода."""

    def __init__(self, sync_engine):
        self.engine = sync_engine
        self.statements: list[str] = []

    def _before(self, conn, cursor, statement, params, context, many):
        self.statements.append(statement)

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._before)
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self.t0
        event.remove(self.engine, "before_cursor_execute", self._before)
        return False


@skip_no_pg
@pytest.mark.asyncio
async def test_pool_query_shape(db, workspace):
    from app.leads import repositories as repo
    from app.leads.selection import (
        LeadSelection,
        order_by,
        selection_conditions,
    )
    from sqlalchemy import select

    from app.leads.models import Lead

    await seed_pool(db, workspace.id)
    await db.flush()

    # Слушатель вешается на синхронный движок под асинхронным.
    bind = db.get_bind()
    sync_engine = getattr(bind, "sync_engine", None) or bind.engine
    selection = LeadSelection.pool(
        cities=[TARGET_CITY, "Москва"], priorities=["A", "B"], q="Компания 01"
    )

    with Counter(sync_engine) as c:
        items, total = await repo.list_pool(
            db, workspace.id, selection, page=1, page_size=50
        )
    list_queries, list_time = len(c.statements), c.elapsed

    with Counter(sync_engine) as c:
        facets = await repo.pool_facets(db, workspace.id, selection)
    facet_queries, facet_time = len(c.statements), c.elapsed

    print("\n--- Базa лидов, 1200 карточек, локальный Postgres ---")
    print(f"список (страница 50 + total): {list_queries} запросов, {list_time*1000:.0f} мс, найдено {total}")
    print(f"счётчики фасетов            : {facet_queries} запросов, {facet_time*1000:.0f} мс")
    print(f"значений в фасетах          : "
          f"{ {k: len(v) for k, v in facets.items()} }")
    print(f"строк на странице           : {len(items)}")

    conds = await selection_conditions(db, selection, workspace.id)
    stmt = select(Lead.id).where(*conds).order_by(*order_by()).limit(50)
    compiled = stmt.compile(
        dialect=sync_engine.dialect, compile_kwargs={"literal_binds": True}
    )
    plan = (await db.execute(text(f"EXPLAIN ANALYZE {compiled}"))).scalars().all()
    print("\n--- EXPLAIN ANALYZE основного запроса ---")
    for line in plan:
        print(f"  {line}")

    # Число запросов не должно расти с числом значений фасета.
    assert facet_queries <= 10, facet_queries
    assert list_queries <= 6, list_queries
