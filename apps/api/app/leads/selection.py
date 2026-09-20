"""Одно описание выборки лидов — и для списка, и для счётчиков, и для
экспорта, и для выдачи «по фильтру» (аудит G6).

До G6 таких описаний было три с половиной, и все разные:

* `repo.list_pool` понимал город, сегмент, fit_min, форму и needs_review —
  по одному значению, без поиска;
* worker экспорта строил свой `WHERE` из десятка ключей, искал `q` только
  по названию компании и не исключал удалённые карточки;
* `assign_pool_by_filter` знал города, сегмент и fit_min;
* остальное — приоритет, tier, тип сделки, источник, теги, наличие почты и
  телефона, текстовый поиск — фильтровал браузер по первым 500 строкам.

Отсюда и брались расхождения: на экране одно, в выгрузке другое, а кнопка
«Выдать по фильтру» работала по третьему набору. Здесь одно описание и один
сборщик условий; все потребители берут их отсюда.

Правила булевой логики (сохранены из интерфейса):

* между разными фасетами — И;
* внутри обычного фасета с множественным выбором — ИЛИ;
* теги — И: карточка обязана нести каждый выбранный тег.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Sequence

from sqlalchemy import Select, and_, cast, func, nullslast, or_
from sqlalchemy.dialects.postgresql import JSONB

from app.leads.models import ASSIGNMENT_STATUSES, Lead

# ---------------------------------------------------------------------------
# Tier
# ---------------------------------------------------------------------------
# Пороги те же, что показывал интерфейс (`tierFromScore` в apps/web/lib/types.ts).
# G6 делает сервер источником истины для них, но значения не меняет: это не
# пересмотр модели скоринга.
TIER_THRESHOLDS: tuple[tuple[str, int], ...] = (
    ("A", 80),
    ("B", 60),
    ("C", 40),
)
TIERS: tuple[str, ...] = ("A", "B", "C", "D")


def tier_for_score(score: int | None) -> str:
    """Tier одной карточки. `score` не бывает NULL (колонка NOT NULL,
    по умолчанию 0), но None трактуем как 0 — на случай вызова с сырым
    словарём."""
    value = score or 0
    for name, threshold in TIER_THRESHOLDS:
        if value >= threshold:
            return name
    return "D"


def _tier_condition(tier: str):
    """Диапазон score для одного tier — как условие SQL."""
    bounds = dict(TIER_THRESHOLDS)
    if tier == "A":
        return Lead.score >= bounds["A"]
    if tier == "B":
        return and_(Lead.score >= bounds["B"], Lead.score < bounds["A"])
    if tier == "C":
        return and_(Lead.score >= bounds["C"], Lead.score < bounds["B"])
    if tier == "D":
        return Lead.score < bounds["C"]
    # Неизвестный tier не должен молча расширять выборку.
    return Lead.id.is_(None)


def tier_case():
    """SQL-выражение «какой tier у строки» — для группировки в счётчиках."""
    from sqlalchemy import case

    bounds = dict(TIER_THRESHOLDS)
    return case(
        (Lead.score >= bounds["A"], "A"),
        (Lead.score >= bounds["B"], "B"),
        (Lead.score >= bounds["C"], "C"),
        else_="D",
    )


# ---------------------------------------------------------------------------
# Текстовый поиск
# ---------------------------------------------------------------------------
_MIN_PHONE_DIGITS = 3  # то же правило, что было в интерфейсе


def _like_escape(value: str) -> str:
    """`%` и `_` в пользовательском запросе — обычные символы.

    В интерфейсе поиск шёл через `String.includes`, где спецсимволов нет.
    Без экранирования `ilike` превратил бы «100%» в «что угодно после 100».
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _text_condition(q: str):
    """Название, почта, ИНН — подстрока без учёта регистра; телефон —
    по цифрам, чтобы «+7 (495) 123-45-67» нашёл «74951234567».

    Телефон сверяется и с нормализованным `phone_e164`, и с цифрами сырого
    `phone`: у карточки с неразобранным номером e164 пустой, а в интерфейсе
    она находилась.
    """
    needle = f"%{_like_escape(q)}%"
    parts = [
        Lead.company_name.ilike(needle, escape="\\"),
        Lead.email.ilike(needle, escape="\\"),
        Lead.inn.ilike(needle, escape="\\"),
    ]
    digits = _digits(q)
    if len(digits) >= _MIN_PHONE_DIGITS:
        phone_needle = f"%{digits}%"
        parts.append(Lead.phone_e164.ilike(phone_needle))
        parts.append(
            func.regexp_replace(
                func.coalesce(Lead.phone, ""), r"[^0-9]", "", "g"
            ).like(phone_needle)
        )
    return or_(*parts)


# ---------------------------------------------------------------------------
# Описание выборки
# ---------------------------------------------------------------------------


def _clean(values: Iterable[str] | None) -> tuple[str, ...]:
    """Пустые строки и дубликаты выбрасываем, порядок сохраняем: пустое
    значение из формы не должно сужать выборку до «поле равно ''»."""
    if not values:
        return ()
    seen: dict[str, None] = {}
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            seen.setdefault(s, None)
    return tuple(seen)


@dataclass(frozen=True)
class LeadSelection:
    """Что именно отобрано. Одно и то же значение ходит по всем путям.

    `assignment_status='pool'` — это и есть «база лидов». Экспорт с других
    экранов передаёт своё значение или ничего.
    """

    cities: tuple[str, ...] = ()
    segments: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    tiers: tuple[str, ...] = ()
    deal_types: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    fit_min: float | None = None
    has_email: bool = False
    has_phone: bool = False
    form_id: uuid.UUID | None = None
    needs_review: bool | None = None
    q: str | None = None
    # Поля, которыми пользуются другие экраны через экспорт.
    assignment_status: str | None = None
    stage_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None

    def __post_init__(self) -> None:
        """Нормализация в одном месте, каким бы путём ни собрали значение.

        Иначе `LeadSelection(cities=[''])` сузила бы выборку до «город равен
        пустой строке», а пробельный `q` искал бы пробел. Сравнение двух
        описаний тоже должно быть осмысленным: после нормализации значение,
        прошедшее через JSON и обратно, равно исходному.
        """
        for key in (
            "cities", "segments", "priorities", "tiers",
            "deal_types", "sources", "tags",
        ):
            object.__setattr__(self, key, _clean(getattr(self, key)))
        text = (self.q or "").strip()
        object.__setattr__(self, "q", text or None)
        object.__setattr__(self, "has_email", bool(self.has_email))
        object.__setattr__(self, "has_phone", bool(self.has_phone))

    def validate_assignment_status(self) -> None:
        """Статус в выборке — из известного набора, иначе отказ.

        `assignment_status` приходит от вызывающего только через экспорт
        (`POST /api/export`, `GET /api/export/snapshot`). Неизвестное
        значение уходило в `WHERE assignment_status = 'zzz'` и давало молча
        пустую выборку: доступ не течёт, но и контракта на входе нет.
        Набор допустимых значений один (`ASSIGNMENT_STATUSES`), тот же
        проверяется на записи в `LeadUpdate`.

        Проверка вызывается явно, а не из `__post_init__`: сначала
        отрабатывает политика доступа (менеджеру всё, кроме `assigned`, —
        403), и только потом формат значения. Иначе неизвестное значение
        меняло бы менеджеру ответ с 403 на 422.
        """
        status = self.assignment_status
        if status and status not in ASSIGNMENT_STATUSES:
            # Импорт внутри: `app.import_export.access` — потребитель этого
            # модуля, держать связь на уровне импорта модуля не за чем.
            from app.import_export.access import ExportFilterInvalid

            raise ExportFilterInvalid(
                "Недопустимое значение assignment_status: "
                f"{status!r}. Допустимы: {', '.join(ASSIGNMENT_STATUSES)}"
            )

    @staticmethod
    def pool(**kwargs: Any) -> "LeadSelection":
        """Выборка в пределах базы лидов."""
        return LeadSelection(assignment_status="pool", **kwargs)

    # -- сериализация ------------------------------------------------------
    # Экспорт живёт в отдельной задаче: выборка уезжает в JSON-колонку и
    # читается обратно worker'ом. Формат один, поэтому пересборки «руками»
    # на той стороне больше нет.

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in (
            "cities", "segments", "priorities", "tiers",
            "deal_types", "sources", "tags",
        ):
            value = getattr(self, key)
            if value:
                out[key] = list(value)
        if self.fit_min is not None:
            out["fit_min"] = float(self.fit_min)
        if self.has_email:
            out["has_email"] = True
        if self.has_phone:
            out["has_phone"] = True
        if self.form_id is not None:
            out["form_id"] = str(self.form_id)
        if self.needs_review is not None:
            out["needs_review"] = bool(self.needs_review)
        if self.q:
            out["q"] = self.q
        if self.assignment_status:
            out["assignment_status"] = self.assignment_status
        if self.stage_id is not None:
            out["stage_id"] = str(self.stage_id)
        if self.assigned_to is not None:
            out["assigned_to"] = str(self.assigned_to)
        return out

    @staticmethod
    def from_json(raw: dict[str, Any] | None) -> "LeadSelection":
        """Разбор сохранённой выборки. Мусор в отдельном ключе не должен
        ронять задачу экспорта и не должен молча расширять выборку — такой
        ключ просто игнорируется, как и раньше."""
        data = dict(raw or {})

        def _uuid(key: str) -> uuid.UUID | None:
            value = data.get(key)
            if not value:
                return None
            try:
                return uuid.UUID(str(value))
            except (ValueError, AttributeError, TypeError):
                return None

        def _float(key: str) -> float | None:
            value = data.get(key)
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _list(key: str, *legacy: str) -> tuple[str, ...]:
            value = data.get(key)
            if value is None:
                # Прежние выгрузки писали одиночные ключи (city, segment…).
                # Читаем и их, иначе повторный запуск старой задачи молча
                # потеряет фильтр.
                for old_key in legacy:
                    single = data.get(old_key)
                    if single:
                        return _clean([single])
                return ()
            if isinstance(value, (list, tuple)):
                return _clean(value)
            return _clean([value])

        needs_review = data.get("needs_review")
        return LeadSelection(
            cities=_list("cities", "city"),
            segments=_list("segments", "segment"),
            priorities=_list("priorities", "priority"),
            tiers=_list("tiers", "tier"),
            deal_types=_list("deal_types", "deal_type"),
            sources=_list("sources", "source"),
            tags=_list("tags"),
            fit_min=_float("fit_min"),
            has_email=bool(data.get("has_email")),
            has_phone=bool(data.get("has_phone")),
            form_id=_uuid("form_id"),
            needs_review=None if needs_review is None else bool(needs_review),
            q=(str(data["q"]).strip() or None) if data.get("q") else None,
            assignment_status=data.get("assignment_status") or None,
            stage_id=_uuid("stage_id"),
            assigned_to=_uuid("assigned_to"),
        )

    @staticmethod
    def from_params(
        *,
        cities: Sequence[str] | None = None,
        segments: Sequence[str] | None = None,
        priorities: Sequence[str] | None = None,
        tiers: Sequence[str] | None = None,
        deal_types: Sequence[str] | None = None,
        sources: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        fit_min: float | None = None,
        has_email: bool = False,
        has_phone: bool = False,
        form_id: uuid.UUID | None = None,
        needs_review: bool | None = None,
        q: str | None = None,
        assignment_status: str | None = None,
    ) -> "LeadSelection":
        """Из параметров запроса. Пустой или пробельный `q` — это отсутствие
        поиска, а не поиск пустоты."""
        text = (q or "").strip()
        return LeadSelection(
            cities=_clean(cities),
            segments=_clean(segments),
            priorities=_clean(priorities),
            tiers=_clean(tiers),
            deal_types=_clean(deal_types),
            sources=_clean(sources),
            tags=_clean(tags),
            fit_min=fit_min,
            has_email=bool(has_email),
            has_phone=bool(has_phone),
            form_id=form_id,
            needs_review=needs_review,
            q=text or None,
            assignment_status=assignment_status,
        )

    def scope_only(self) -> "LeadSelection":
        """Только то, что задаёт границы пула: форма и needs_review.

        Счётчики фасетов считаются по этой выборке. Так было и до G6:
        число рядом с «Кофейни и кафе» показывает, сколько таких карточек
        в пуле, а не сколько их осталось после уже выбранных фильтров —
        иначе каждый невыбранный фасет показывал бы ноль.
        """
        return LeadSelection(
            form_id=self.form_id,
            needs_review=self.needs_review,
            assignment_status=self.assignment_status,
            stage_id=self.stage_id,
            assigned_to=self.assigned_to,
        )

    def with_(self, **kwargs: Any) -> "LeadSelection":
        return replace(self, **kwargs)


# ---------------------------------------------------------------------------
# Сборка условий
# ---------------------------------------------------------------------------


async def resolve_form_slug(db, form_id: uuid.UUID, workspace_id: uuid.UUID):
    """Форма живёт в другом домене; `source` у лида хранит `form:<slug>`."""
    from app.leads.repositories import _slug_for_form_id

    return await _slug_for_form_id(db, form_id, workspace_id)


class NoMatches(Exception):
    """Фильтр ссылается на то, чего в этом пространстве нет, — выборка
    гарантированно пуста. Отдельное исключение, чтобы вызывающий вернул
    пустую страницу, а не молча снял фильтр."""


async def selection_conditions(
    db, selection: LeadSelection, workspace_id: uuid.UUID
) -> list:
    """Список условий для `WHERE`. Единственное место, где описание
    выборки превращается в SQL."""
    conds = [
        Lead.workspace_id == workspace_id,
        Lead.deleted_at.is_(None),
    ]

    if selection.assignment_status:
        conds.append(Lead.assignment_status == selection.assignment_status)
    if selection.stage_id is not None:
        conds.append(Lead.stage_id == selection.stage_id)
    if selection.assigned_to is not None:
        conds.append(Lead.assigned_to == selection.assigned_to)

    if selection.form_id is not None:
        slug = await resolve_form_slug(db, selection.form_id, workspace_id)
        if slug is None:
            # Неизвестная или удалённая форма — и чужая форма тоже: поиск
            # идёт в пределах пространства, поэтому подсунуть form_id из
            # соседнего workspace нельзя.
            raise NoMatches()
        conds.append(Lead.source == f"form:{slug}")

    if selection.needs_review is True:
        conds.append(Lead.needs_review.is_(True))
    elif selection.needs_review is False:
        conds.append(Lead.needs_review.is_(False))

    # ИЛИ внутри фасета, И между фасетами.
    if selection.cities:
        conds.append(Lead.city.in_(selection.cities))
    if selection.segments:
        conds.append(Lead.segment.in_(selection.segments))
    if selection.priorities:
        conds.append(Lead.priority.in_(selection.priorities))
    if selection.deal_types:
        conds.append(Lead.deal_type.in_(selection.deal_types))
    if selection.sources:
        conds.append(Lead.source.in_(selection.sources))
    if selection.tiers:
        conds.append(or_(*[_tier_condition(t) for t in selection.tiers]))

    # Теги — И: карточка обязана нести каждый выбранный.
    # `tags_json` объявлена как JSON, поэтому приводим к JSONB: оператор
    # containment есть только у него.
    for tag in selection.tags:
        conds.append(cast(Lead.tags_json, JSONB).contains([tag]))

    if selection.fit_min is not None:
        conds.append(Lead.fit_score >= selection.fit_min)
    if selection.has_email:
        conds.append(and_(Lead.email.isnot(None), Lead.email != ""))
    if selection.has_phone:
        conds.append(and_(Lead.phone.isnot(None), Lead.phone != ""))

    if selection.q:
        conds.append(_text_condition(selection.q))

    return conds


def order_by():
    """Порядок списка. Прежний бизнес-порядок плюс идентификатор третьим
    ключом: `fit_score` и `created_at` совпадают у импортированных пачками
    карточек, а без полного порядка соседние страницы теряют и повторяют
    строки."""
    return (
        nullslast(Lead.fit_score.desc()),
        Lead.created_at.asc(),
        Lead.id.asc(),
    )
