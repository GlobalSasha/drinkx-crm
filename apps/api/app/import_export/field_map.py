"""Canonical lead-import fields + alias dictionary for fuzzy mapping.

This is the single source of truth for "what columns can we import into a
Lead". Used by:
  - mapper.suggest_mapping (header → field key)
  - mapper.apply_mapping (rename source rows to canonical keys)
  - validators.validate_row (per-field validation rules)
  - bulk_import_run (which fields land where on the Lead model)

Only company_name is required. Everything else is best-effort — a row
missing optional fields still imports.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldDef:
    key: str
    label_ru: str
    aliases: tuple[str, ...] = ()
    required: bool = False


# Order matters only for stable iteration (status APIs / docs); mapper
# scoring is alias-driven, not order-driven.
LEAD_IMPORT_FIELDS: dict[str, FieldDef] = {
    "company_name": FieldDef(
        key="company_name",
        label_ru="Название компании",
        aliases=("название", "компания", "name", "company", "название компании"),
        required=True,
    ),
    "segment": FieldDef(
        key="segment",
        label_ru="Сегмент",
        aliases=("сегмент", "segment", "тип", "category", "категория"),
    ),
    "city": FieldDef(
        key="city",
        label_ru="Город",
        aliases=("город", "city", "регион", "region"),
    ),
    "email": FieldDef(
        key="email",
        label_ru="Email",
        aliases=("email", "почта", "e-mail", "e mail", "электронная почта"),
    ),
    "phone": FieldDef(
        key="phone",
        label_ru="Телефон",
        aliases=("телефон", "phone", "тел", "tel", "мобильный"),
    ),
    "website": FieldDef(
        key="website",
        label_ru="Сайт",
        aliases=("сайт", "website", "url", "сайт компании", "domain"),
    ),
    "inn": FieldDef(
        key="inn",
        label_ru="ИНН",
        aliases=("инн", "inn", "tax_id", "налоговый номер"),
    ),
    "deal_amount": FieldDef(
        key="deal_amount",
        label_ru="Сумма сделки",
        aliases=("сумма", "amount", "deal", "бюджет", "budget", "сумма сделки"),
    ),
    "source": FieldDef(
        key="source",
        label_ru="Источник",
        aliases=("источник", "source", "откуда"),
    ),
    "tags": FieldDef(
        key="tags",
        label_ru="Теги",
        aliases=("теги", "tags", "метки", "labels"),
    ),
    "priority": FieldDef(
        key="priority",
        label_ru="Приоритет",
        aliases=("приоритет", "priority", "tier"),
    ),
    "deal_type": FieldDef(
        key="deal_type",
        label_ru="Тип сделки",
        aliases=("тип сделки", "deal_type", "deal type"),
    ),
    "notes": FieldDef(
        key="notes",
        label_ru="Заметки",
        aliases=("заметки", "notes", "комментарий", "comment", "примечание"),
    ),
}


# Subset that maps directly onto a Lead column. The rest (deal_amount,
# notes) are attached to the new lead as an import-Activity comment so
# we don't drop user data on import.
DIRECT_LEAD_COLUMNS: frozenset[str] = frozenset({
    "company_name", "segment", "city", "email", "phone",
    "website", "inn", "source", "priority", "deal_type",
})

# Stored as the lead's tags_json column after splitting on comma.
TAG_FIELD: str = "tags"

# Surfaced into a single Activity(type='comment') row attached to the lead.
EXTRAS_FOR_COMMENT: tuple[str, ...] = ("deal_amount", "notes")
