"""Normalize companies.primary_segment to Russian labels (canonical format).

Lead.segment stores Russian labels verbatim ("Продуктовый ритейл",
"QSR / Fast Food", "АЗС", ...). Company.primary_segment was populated
by base_update's LLM extraction with English slugs ("food_retail",
"qsr_fast_food", "gas_stations", ...). This migration normalises
companies.primary_segment to the same Russian-label format so both
columns can be queried + displayed consistently without a frontend
mapping hack.

Migration rolls back to slug form on downgrade for symmetry, though
in practice once normalised we'd keep RU forever.

Revision ID: 0040_normalize_company_segments
Revises: 0039_quotas_table
Create Date: 2026-05-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0040_normalize_company_segments"
down_revision = "0039_quotas_table"
branch_labels = None
depends_on = None


# Slug → canonical Russian label (matches frontend SEGMENT_OPTIONS in i18n.ts).
_SLUG_TO_LABEL = {
    "food_retail":                    "Продуктовый ритейл",
    "non_food_retail":                "Непродуктовый ритейл",
    "coffee_shops":                   "Кофейни и кафе",
    "qsr_fast_food":                  "QSR / Fast Food",
    "qsr":                            "QSR / Fast Food",
    "horeca":                         "HORECA",
    "gas_stations":                   "АЗС",
    "coffee_equipment_distributors":  "Дистрибьюторы оборудования",
    "raw_materials":                  "Зерно обжарка экстракт",
    "vending":                        "Вендинг",
    "other":                          "Другое",
}


def upgrade() -> None:
    bind = op.get_bind()
    for slug, label in _SLUG_TO_LABEL.items():
        bind.execute(
            sa.text("UPDATE companies SET primary_segment = :label WHERE primary_segment = :slug"),
            {"label": label, "slug": slug},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for slug, label in _SLUG_TO_LABEL.items():
        bind.execute(
            sa.text("UPDATE companies SET primary_segment = :slug WHERE primary_segment = :label"),
            {"label": label, "slug": slug},
        )
