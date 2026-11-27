"""Входной этап воронки и этапы «ещё не сделка».

Раньше «первым этапом» считался этап с наименьшей позицией. В рабочей
воронке столбец «Не отвечает» поставили самым левым, и всё поехало: новые
лиды из загрузки и мессенджеров вставали на «Не отвечает», лиды на «Первом
контакте» попадали в «застрявшие сделки», а заявки с сайта пропадали из
«Входящих» как будто по ним уже работают.

Теперь так:
- этап-стоянка — этап, в названии которого есть «не отвеча» (лид не
  отвечает, его отложили); на него лиды не заводятся;
- входной этап — самый левый этап воронки, кроме стоянки и закрытых
  («Выиграно» / «Отказ»): сюда встают новые лиды, тут ждут заявки;
- «ещё не сделка» — входной этап и стоянка: такие лиды не считаются
  застрявшими сделками, а идут отдельной строкой.
"""
from __future__ import annotations

from sqlalchemy import ColumnElement, func, not_, select
from sqlalchemy.orm import aliased

from app.pipelines.models import Stage

PARKING_MARK = "не отвеча"


def is_parking(name: str | None) -> bool:
    return PARKING_MARK in (name or "").lower()


def pick_entry_stage(stages: list[Stage]) -> Stage | None:
    """Входной этап из этапов одной воронки; если подходящих нет — самый левый."""
    ordered = sorted(stages, key=lambda s: s.position)
    for s in ordered:
        if not (s.is_won or s.is_lost or is_parking(s.name)):
            return s
    return ordered[0] if ordered else None


# --- SQL-фрагменты для сырых запросов; этап лида там зовётся `s`. ---

_ENTRY_POSITION_SQL = f"""(
    SELECT min(s2.position) FROM stages s2
    WHERE s2.pipeline_id = s.pipeline_id
      AND s2.is_won = false AND s2.is_lost = false
      AND lower(s2.name) NOT LIKE '%{PARKING_MARK}%'
)"""

# Лид на входном этапе или на стоянке — это ещё не сделка.
NOT_A_DEAL_YET_SQL = (
    f"(s.position = {_ENTRY_POSITION_SQL} OR lower(s.name) LIKE '%{PARKING_MARK}%')"
)


def on_entry_stage(stage: type[Stage], pipeline_id: ColumnElement) -> ColumnElement[bool]:
    """Условие SQLAlchemy: `stage` — входной этап воронки `pipeline_id`."""
    s2 = aliased(Stage)
    entry_position = (
        select(func.min(s2.position))
        .where(
            s2.pipeline_id == pipeline_id,
            s2.is_won.is_(False),
            s2.is_lost.is_(False),
            not_(func.lower(s2.name).contains(PARKING_MARK)),
        )
        .correlate_except(s2)
        .scalar_subquery()
    )
    return stage.position == entry_position
