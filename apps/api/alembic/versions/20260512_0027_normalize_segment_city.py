"""0027_normalize_segment_city — collapse legacy segment values to the
canonical 8-key vocabulary (ADR-023) and normalize `leads.city`.

Revision ID: 0027_normalize_segment_city
Revises: 0026_leads_messenger_ids
Create Date: 2026-05-12

Sprint 3.5 G2.

What this migration does (data-only — no schema change):

1. Rename legacy slug `coffee_equipment_distributors` → `distributor`
   on `leads.segment` and `companies.primary_segment`.
2. Map free-text Russian / English variants ("HoReCa", "Офисы",
   "Ритейл", "Производство", etc.) that may have been typed into
   manually-created leads to the closest canonical key. Unknown
   values are LEFT AS-IS so the post-migration audit query
   (in self-check) can find and triage them.
3. Normalize `leads.city` and `companies.city` — strip "г." prefix,
   trim, capitalize first letter. Implemented in Python (reuses
   `app.leads.constants.normalize_city`) since the same regex is
   already used at the API boundary.

ADR-020: widen alembic_version first.

Reversibility: this is a data migration, not a schema change. The
downgrade restores `distributor` → `coffee_equipment_distributors`
for traceability; the free-text mapping is one-way (we don't know
which original spelling each row had) and city normalization is
not reversible.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0027_normalize_segment_city"
down_revision: Union[str, None] = "0026_leads_messenger_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Free-text → canonical key. Lowercased + ILIKE-style %% wrappers
# applied at SQL time. Order matters: more specific patterns first
# so e.g. "Непродуктовый ритейл" doesn't slip into "Продуктовый ритейл".
_FREE_TEXT_RULES: list[tuple[str, str]] = [
    # non-food retail (check before food retail)
    ("%непродуктов%",         "non_food_retail"),
    ("%non%food%retail%",     "non_food_retail"),
    ("%нонфуд%",              "non_food_retail"),
    # food retail
    ("%продуктов%",           "food_retail"),
    ("%food%retail%",         "food_retail"),
    # coffee / cafe / restaurants
    ("%кофейн%",              "coffee_shops"),
    ("%кафе%",                "coffee_shops"),
    ("%ресторан%",            "coffee_shops"),
    ("%horeca%",              "coffee_shops"),
    ("%хорека%",              "coffee_shops"),
    # QSR
    ("%qsr%",                 "qsr_fast_food"),
    ("%fast%food%",           "qsr_fast_food"),
    ("%фастфуд%",             "qsr_fast_food"),
    # АЗС
    ("%азс%",                 "gas_stations"),
    ("%заправ%",              "gas_stations"),
    ("%petrol%",              "gas_stations"),
    # office
    ("%офис%",                "office"),
    ("%office%",              "office"),
    # hotel
    ("%отел%",                "hotel"),
    ("%hotel%",               "hotel"),
    # distributor
    ("%дистриб%",             "distributor"),
    ("%distributor%",         "distributor"),
]


def _normalize_city_py(value: str | None) -> str | None:
    """Inlined for migration isolation — keeps the migration importable
    even if `app/leads/constants.py` later moves or renames. Mirrors
    `app.leads.constants.normalize_city` byte-for-byte; tests in
    `test_leads_constants.py` cover the canonical implementation.
    """
    import re

    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    s = re.sub(r"^г\.?\s+|^г\.\s*", "", s, flags=re.IGNORECASE).strip()
    if not s:
        return None
    return s[0].upper() + s[1:]


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    conn = op.get_bind()

    # ----- 1. legacy slug rename -----
    conn.execute(
        text(
            "UPDATE leads SET segment = 'distributor' "
            "WHERE segment = 'coffee_equipment_distributors'"
        )
    )
    conn.execute(
        text(
            "UPDATE companies SET primary_segment = 'distributor' "
            "WHERE primary_segment = 'coffee_equipment_distributors'"
        )
    )

    # ----- 2. free-text → slug mapping -----
    # Only rewrite values that are NOT already canonical. The IN-list
    # keeps the canonical 8 untouched even if their lowercase form
    # matches one of the patterns (e.g. "office" matches "%office%"
    # but is already canonical and should not be re-touched).
    canonical_in = (
        "('food_retail','non_food_retail','coffee_shops','qsr_fast_food',"
        "'gas_stations','office','hotel','distributor')"
    )
    for pattern, target in _FREE_TEXT_RULES:
        conn.execute(
            text(
                f"UPDATE leads SET segment = :tgt "
                f"WHERE segment IS NOT NULL "
                f"AND segment NOT IN {canonical_in} "
                f"AND lower(segment) LIKE :pat"
            ),
            {"tgt": target, "pat": pattern},
        )
        conn.execute(
            text(
                f"UPDATE companies SET primary_segment = :tgt "
                f"WHERE primary_segment IS NOT NULL "
                f"AND primary_segment NOT IN {canonical_in} "
                f"AND lower(primary_segment) LIKE :pat"
            ),
            {"tgt": target, "pat": pattern},
        )

    # ----- 3. city normalization (Python loop, since the regex is
    # locale-aware and easier to maintain in one place) -----
    for tbl in ("leads", "companies"):
        rows = conn.execute(
            text(
                f"SELECT id, city FROM {tbl} "
                f"WHERE city IS NOT NULL AND length(trim(city)) > 0"
            )
        ).fetchall()
        for row_id, raw_city in rows:
            normalized = _normalize_city_py(raw_city)
            if normalized != raw_city:
                conn.execute(
                    text(f"UPDATE {tbl} SET city = :c WHERE id = :id"),
                    {"c": normalized, "id": row_id},
                )

    # ----- 4. audit print -----
    leads_by_segment = conn.execute(
        text(
            "SELECT segment, count(*) FROM leads "
            "WHERE segment IS NOT NULL GROUP BY segment ORDER BY count(*) DESC"
        )
    ).fetchall()
    unmapped = conn.execute(
        text(
            "SELECT count(*) FROM leads "
            "WHERE segment IS NOT NULL "
            f"AND segment NOT IN {canonical_in}"
        )
    ).scalar()
    print("0027_normalize_segment_city — leads.segment distribution:")
    for seg, n in leads_by_segment:
        print(f"  {seg:<32} {n}")
    print(f"  UNMAPPED (manual review): {unmapped}")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE leads SET segment = 'coffee_equipment_distributors' "
            "WHERE segment = 'distributor'"
        )
    )
    conn.execute(
        text(
            "UPDATE companies SET primary_segment = 'coffee_equipment_distributors' "
            "WHERE primary_segment = 'distributor'"
        )
    )
    # City normalization + free-text → slug mapping are NOT reversed
    # — the original variants are gone.
