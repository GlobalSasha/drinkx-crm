"""Fixed categories for «Голос клиентов» — what the AI may tag a comment with.

The AI only sorts text into these boxes and must quote the comment; anything
outside the list is dropped on ingest. Edit the list here (and the prompt in
tools/voice-worker reads it from GET /worker/v1/insights/pending).
"""
from __future__ import annotations

# key -> (group, label). Groups: objection, question, interest, contact.
CATEGORIES: dict[str, tuple[str, str]] = {
    # Возражения
    "price": ("objection", "Цена, дорого"),
    "leasing": ("objection", "Нужен лизинг или рассрочка"),
    "vat": ("objection", "НДС"),
    "format_doubts": ("objection", "Сомнения в формате или качестве"),
    "not_now": ("objection", "Не сейчас, отложил"),
    "not_decision_maker": ("objection", "Не тот, кто решает"),
    "installation": ("objection", "Монтаж, место, подключение"),
    "service_concerns": ("objection", "Сервис и обслуживание"),
    "chose_other": ("objection", "Выбрали другое решение"),
    # Вопросы
    "asks_price": ("question", "Спрашивают цену"),
    "integration": ("question", "Интеграция со своим оборудованием"),
    "technical": ("question", "Техника: промывка, настройки, рецепты"),
    "see_live": ("question", "Хотят увидеть вживую или протестировать"),
    "dealer_terms": ("question", "Дилерские и оптовые условия"),
    "delivery": ("question", "Доставка и сроки"),
    # Интерес
    "wants_pilot": ("interest", "Хотят тест или пилот"),
    "wants_quote": ("interest", "Просят КП"),
    "network_scale": ("interest", "Сеть, много точек"),
    # Связь
    "no_answer": ("contact", "Не дозвониться, номер не работает"),
    # Конкуренты — название в отдельном поле
    "competitor": ("competitor", "Упоминают конкурента"),
}

GROUP_LABELS: dict[str, str] = {
    "objection": "Возражения",
    "question": "О чём спрашивают",
    "interest": "Интерес",
    "competitor": "Конкуренты",
    "contact": "Связь",
}

# Spellings that should count as one competitor. Anything else the AI names
# is kept as written (trimmed) — the list only glues variants together.
COMPETITOR_ALIASES: dict[str, str] = {
    "scanomat": "Scanomat",
    "сканомат": "Scanomat",
    "easy system": "Easy System",
    "easysystem": "Easy System",
    "изи систем": "Easy System",
    "изисистем": "Easy System",
    "uvenco": "Uvenco",
    "увенко": "Uvenco",
}


def normalize_competitor(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = " ".join(name.split()).strip(" .,;:\"'«»")[:80]
    if not cleaned:
        return None
    return COMPETITOR_ALIASES.get(cleaned.lower(), cleaned)
