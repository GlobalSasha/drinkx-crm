"""Города и продукты для статистики на /today: разбор текста, без базы.

Город: поле карточки, иначе «Город» из заявки с сайта. Продукт: поля карточки
(оборудование, бренд) и то, что клиент написал в заявке. Комментарии менеджеров
не читаем намеренно: «клиент не хочет S400» посчиталось бы как интерес к S400.
"""
from __future__ import annotations

import re
from typing import Any

from app.forms.lead_factory import (
    QUESTION_KEYS,
    _lookup,
    _normalize_key,
    _parse_labeled_block,
    _project_payload,
    extract_question,
)

PRODUCTS: tuple[str, ...] = ("S100", "S200", "S300", "S400", "AeroMilk")

# Кириллическая «с» только вплотную к числу: «с 100 точками» — не модель.
_MODEL_RE = re.compile(
    r"(?<![a-zа-яё0-9])(?:s[\s-]?|с)(100|200|300|400)(?!\d)", re.IGNORECASE
)
_AEROMILK_RE = re.compile(r"aero\s*milk|аэро\s*милк", re.IGNORECASE)

_CITY_LABELS = {"город", "city"}
_PRODUCT_LABELS = {"интересует модель", "модель", "продукт"}

_CITY_PREFIX_RE = re.compile(r"^(?:г\.|г\s|гор\.|город\s)\s*", re.IGNORECASE)
_CITY_ALIASES = {
    "мск": "москва",
    "moscow": "москва",
    "спб": "санкт-петербург",
    "питер": "санкт-петербург",
    "санкт петербург": "санкт-петербург",
    "saint petersburg": "санкт-петербург",
    "st. petersburg": "санкт-петербург",
    "ростов на дону": "ростов-на-дону",
    # Опечатки и падеж, которые реально встретились в базе.
    "москве": "москва",
    "москава": "москва",
    "москвв": "москва",
    "москвка": "москва",
}
_TWO_WORD_CITIES = ("нижний новгород", "набережные челны")
_LOWERCASE_WORDS = {"на", "над", "под", "де", "и"}


def normalize_city(raw: str | None) -> str | None:
    """Привести написание к одному виду, чтобы «г. москва» и «Москва» были
    одним городом. В поле часто лежит весь адрес: от него оставляем город."""
    city = " ".join((raw or "").split())
    city = _CITY_PREFIX_RE.sub("", city).strip(" .,").casefold()
    city = city.split(",")[0].strip().replace(" - ", "-")
    if not city:
        return None
    if any(ch.isdigit() for ch in city):  # «Москва Маросейка 11»
        city = next(
            (c for c in _TWO_WORD_CITIES if city.startswith(c)), city.split(" ")[0]
        )
    city = _CITY_ALIASES.get(city, city)

    def title(word: str, first: bool) -> str:
        return word if word in _LOWERCASE_WORDS and not first else word.capitalize()

    return " ".join(
        "-".join(
            title(part, first=i == 0 and j == 0)
            for j, part in enumerate(word.split("-"))
        )
        for i, word in enumerate(city.split(" "))
    )


def find_products(*texts: str | None) -> set[str]:
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        found.update(f"S{m}" for m in _MODEL_RE.findall(text))
        if _AEROMILK_RE.search(text):
            found.add("AeroMilk")
    return found


def _labeled(payload: Any, labels: set[str]) -> list[str]:
    pairs = _parse_labeled_block(_lookup(payload, QUESTION_KEYS))
    return [value for label, value in pairs if _normalize_key(label) in labels]


def city_from_payload(payload: Any) -> str | None:
    values = _labeled(payload, _CITY_LABELS)
    return values[0] if values else _project_payload(payload).get("city")


def products_from_payload(payload: Any) -> set[str]:
    return find_products(
        *_labeled(payload, _PRODUCT_LABELS),
        extract_question(payload, limit=4000),
    )
