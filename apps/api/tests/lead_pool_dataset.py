"""Замороженный набор лидов для проверок пула (аудит G6).

1200 карточек в пуле одного рабочего пространства плюс одна «целевая» —
её и ищут все сценарии. Целевая карточка стоит далеко за прежней границей
первой страницы (500) и одновременно единственная, кто подходит под
несколько фильтров, которые раньше применялись в браузере.

Набор детерминированный: одни и те же атрибуты при каждом прогоне, поэтому
списки идентификаторов из списка и из экспорта можно сравнивать напрямую.

Используется и воспроизведением (`repro_g6_lead_pool.py`), и регрессиями
(`test_lead_pool_selection.py`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

POOL_SIZE = 1200

# Целевая карточка — та, которую до G6 нельзя было найти.
TARGET_NAME = "Целевая Кофейня За Границей Страницы"
TARGET_CITY = "Казань"
TARGET_SEGMENT = "Кофейни и кафе"
TARGET_PRIORITY = "A"
TARGET_DEAL_TYPE = "station"
TARGET_SOURCE = "outbound"
TARGET_TAGS = ["vip", "2026"]
TARGET_EMAIL = "Target.Lead@Example.COM"
TARGET_PHONE = "+7 (495) 123-45-67"
TARGET_INN = "7712345678"
TARGET_SCORE = 85          # tier A
TARGET_FIT = 27.0          # низкий fit: карточка уезжает в конец списка
TARGET_INDEX = 900         # позиция в порядке сортировки, далеко за 500

# Остальные карточки. Ни одна из них не должна случайно совпасть с целевой
# по отличительным признакам, иначе проверки перестанут что-либо значить.
OTHER_CITIES = ["Москва", "Санкт-Петербург", "Новосибирск"]
OTHER_SEGMENTS = ["АЗС", "Ритейл", "HoReCa"]
OTHER_PRIORITIES = ["B", "C"]
OTHER_DEAL_TYPES = ["rent", "service"]
OTHER_SOURCES = ["import", "site"]

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _fit_for(index: int) -> float:
    """Убывающая шкала: порядок списка совпадает с порядком индексов."""
    return round(99.0 - index * 0.06, 2)


async def seed_pool(db, workspace_id: uuid.UUID, *, size: int = POOL_SIZE):
    """Создаёт набор и возвращает (target_lead, all_ids_in_sort_order).

    Пишет через bulk insert, а не через репозиторий: 1200 ORM-объектов с
    валидаторами заметно медленнее, а проверяем мы выборку, не запись.
    Нормализованные поля (`phone_e164`, `email_normalized`) заполняются
    теми же хелперами, что и валидаторы модели.
    """
    from sqlalchemy import insert

    from app.common.email import email_domain_criterion, normalize_email
    from app.common.phone import to_e164
    from app.leads.models import Lead

    rows: list[dict] = []
    target_id: uuid.UUID | None = None
    # На полном наборе целевая карточка стоит за прежней границей в 500.
    # Маленькие наборы (проверки прав, форм, корзины) всё равно должны её
    # содержать — иначе у них нет отличимой строки.
    target_index = min(TARGET_INDEX, size - 1)

    for i in range(size):
        lead_id = uuid.uuid4()
        is_target = i == target_index
        if is_target:
            target_id = lead_id
            name = TARGET_NAME
            city, segment = TARGET_CITY, TARGET_SEGMENT
            priority, deal_type = TARGET_PRIORITY, TARGET_DEAL_TYPE
            source, tags = TARGET_SOURCE, list(TARGET_TAGS)
            email, phone, inn = TARGET_EMAIL, TARGET_PHONE, TARGET_INN
            score = TARGET_SCORE
        else:
            name = f"Компания {i:04d}"
            # Каждая тридцатая — тоже в Казани. Так фильтр по городу
            # целевой карточки отбирает осмысленный набор, а не одну строку,
            # и расхождение экспорта видно на десятках идентификаторов.
            city = (
                TARGET_CITY if i % 30 == 0 else OTHER_CITIES[i % len(OTHER_CITIES)]
            )
            segment = OTHER_SEGMENTS[i % len(OTHER_SEGMENTS)]
            priority = OTHER_PRIORITIES[i % len(OTHER_PRIORITIES)]
            deal_type = OTHER_DEAL_TYPES[i % len(OTHER_DEAL_TYPES)]
            source = OTHER_SOURCES[i % len(OTHER_SOURCES)]
            # Тег «vip» есть у каждой десятой, «2026» — у каждой седьмой.
            # Пересечение обеих меток даёт немного карточек, поэтому
            # AND-семантику тегов видно по числу, а не по нулю.
            tags = []
            if i % 10 == 0:
                tags.append("vip")
            if i % 7 == 0:
                tags.append("2026")
            # Почта у каждой третьей, телефон у каждой пятой.
            email = f"lead{i:04d}@example.com" if i % 3 == 0 else None
            phone = f"+7495{i:07d}" if i % 5 == 0 else None
            inn = f"77{i:08d}" if i % 4 == 0 else None
            # Ниже порога tier A: целевая карточка остаётся единственной «A».
            score = 40 + (i % 39)

        rows.append(
            dict(
                id=lead_id,
                workspace_id=workspace_id,
                company_name=name,
                city=city,
                segment=segment,
                priority=priority,
                deal_type=deal_type,
                source=source,
                tags_json=tags,
                email=email,
                email_normalized=normalize_email(email),
                email_domain_criterion=email_domain_criterion(normalize_email(email)),
                phone=phone,
                phone_e164=to_e164(phone),
                inn=inn,
                score=score,
                fit_score=TARGET_FIT if is_target else _fit_for(i),
                assignment_status="pool",
                needs_review=False,
                created_at=EPOCH + timedelta(minutes=i),
                updated_at=EPOCH + timedelta(minutes=i),
            )
        )

    await db.execute(insert(Lead), rows)
    await db.flush()
    assert target_id is not None
    return target_id, [r["id"] for r in rows]
