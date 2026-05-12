"""Sprint 3.5 — dry-run preview for migration 0027 (segment + city normalization).

Opens ONE transaction, runs the same UPDATEs as
`alembic/versions/20260512_0027_normalize_segment_city.py`, prints
before/after segment distributions + UNMAPPED count + city-normalization
diff count, then ROLLBACKs.

Zero writes commit. Safe to run against production.

Uses asyncpg directly — matches `scripts/backfill_companies.py`.

Usage (inside the api container on prod — note `uv run`, the app's deps
live in a uv-managed venv that plain `python` won't see):

    docker compose -f /opt/drinkx-crm/infra/production/docker-compose.yml \\
        exec -T api uv run python /opt/drinkx-crm/scripts/dryrun_0027_segment_city.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from typing import Any


CANONICAL_KEYS: list[str] = [
    "food_retail",
    "non_food_retail",
    "coffee_shops",
    "qsr_fast_food",
    "gas_stations",
    "office",
    "hotel",
    "distributor",
]

# Order matters — more specific patterns first.
FREE_TEXT_RULES: list[tuple[str, str]] = [
    ("%непродуктов%",     "non_food_retail"),
    ("%non%food%retail%", "non_food_retail"),
    ("%нонфуд%",          "non_food_retail"),
    ("%продуктов%",       "food_retail"),
    ("%food%retail%",     "food_retail"),
    ("%кофейн%",          "coffee_shops"),
    ("%кафе%",            "coffee_shops"),
    ("%ресторан%",        "coffee_shops"),
    ("%horeca%",          "coffee_shops"),
    ("%хорека%",          "coffee_shops"),
    ("%qsr%",             "qsr_fast_food"),
    ("%fast%food%",       "qsr_fast_food"),
    ("%фастфуд%",         "qsr_fast_food"),
    ("%азс%",             "gas_stations"),
    ("%заправ%",          "gas_stations"),
    ("%petrol%",          "gas_stations"),
    ("%офис%",            "office"),
    ("%office%",          "office"),
    ("%отел%",            "hotel"),
    ("%hotel%",           "hotel"),
    ("%дистриб%",         "distributor"),
    ("%distributor%",     "distributor"),
]

CANONICAL_IN_SQL = (
    "('food_retail','non_food_retail','coffee_shops','qsr_fast_food',"
    "'gas_stations','office','hotel','distributor')"
)


def normalize_city(value: str | None) -> str | None:
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    s = re.sub(r"^г\.?\s+|^г\.\s*", "", s, flags=re.IGNORECASE).strip()
    if not s:
        return None
    return s[0].upper() + s[1:]


def _fmt_count_table(rows: list[tuple[str | None, int]], width: int = 36) -> str:
    if not rows:
        return "  (no rows)"
    out: list[str] = []
    for seg, n in rows:
        label = seg if seg is not None else "<NULL>"
        out.append(f"  {label:<{width}} {n:>6}")
    return "\n".join(out)


async def _segment_counts(
    conn: Any, table: str, col: str
) -> list[tuple[str | None, int]]:
    rows = await conn.fetch(
        f"SELECT {col} AS seg, count(*) AS n FROM {table} "
        f"GROUP BY {col} ORDER BY n DESC, {col} NULLS LAST"
    )
    return [(r["seg"], r["n"]) for r in rows]


async def _city_diff_count(conn: Any, table: str) -> tuple[int, int]:
    rows = await conn.fetch(
        f"SELECT id, city FROM {table} "
        f"WHERE city IS NOT NULL AND length(trim(city)) > 0"
    )
    total = len(rows)
    changed = sum(1 for r in rows if normalize_city(r["city"]) != r["city"])
    return total, changed


async def main() -> int:
    import asyncpg

    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("✗ DATABASE_URL not set", file=sys.stderr)
        return 2
    # asyncpg uses libpq scheme — strip SQLAlchemy's "+asyncpg" suffix.
    db_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(db_url)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            print("=" * 60)
            print("DRY-RUN — migration 0027_normalize_segment_city")
            print("=" * 60)

            # ----- BEFORE -----
            print("\n[BEFORE] leads.segment:")
            before_leads = await _segment_counts(conn, "leads", "segment")
            print(_fmt_count_table(before_leads))

            print("\n[BEFORE] companies.primary_segment:")
            before_companies = await _segment_counts(
                conn, "companies", "primary_segment"
            )
            print(_fmt_count_table(before_companies))

            # ----- 1. legacy slug rename -----
            r1 = await conn.execute(
                "UPDATE leads SET segment = 'distributor' "
                "WHERE segment = 'coffee_equipment_distributors'"
            )
            r2 = await conn.execute(
                "UPDATE companies SET primary_segment = 'distributor' "
                "WHERE primary_segment = 'coffee_equipment_distributors'"
            )
            print(
                f"\nStep 1 — rename coffee_equipment_distributors → distributor: "
                f"leads={r1.split()[-1]} companies={r2.split()[-1]}"
            )

            # ----- 2. free-text → slug -----
            for pattern, target in FREE_TEXT_RULES:
                await conn.execute(
                    f"UPDATE leads SET segment = $1 "
                    f"WHERE segment IS NOT NULL "
                    f"AND segment NOT IN {CANONICAL_IN_SQL} "
                    f"AND lower(segment) LIKE $2",
                    target, pattern,
                )
                await conn.execute(
                    f"UPDATE companies SET primary_segment = $1 "
                    f"WHERE primary_segment IS NOT NULL "
                    f"AND primary_segment NOT IN {CANONICAL_IN_SQL} "
                    f"AND lower(primary_segment) LIKE $2",
                    target, pattern,
                )
            print("Step 2 — free-text → canonical mapping applied")

            # ----- 3. city normalization -----
            for tbl in ("leads", "companies"):
                total, changed = await _city_diff_count(conn, tbl)
                print(
                    f"Step 3 — {tbl}.city normalization: "
                    f"{changed}/{total} rows would change"
                )
                rows = await conn.fetch(
                    f"SELECT id, city FROM {tbl} "
                    f"WHERE city IS NOT NULL AND length(trim(city)) > 0"
                )
                for r in rows:
                    n = normalize_city(r["city"])
                    if n != r["city"]:
                        await conn.execute(
                            f"UPDATE {tbl} SET city = $1 WHERE id = $2",
                            n, r["id"],
                        )

            # ----- AFTER -----
            print("\n[AFTER] leads.segment:")
            after_leads = await _segment_counts(conn, "leads", "segment")
            print(_fmt_count_table(after_leads))

            print("\n[AFTER] companies.primary_segment:")
            after_companies = await _segment_counts(
                conn, "companies", "primary_segment"
            )
            print(_fmt_count_table(after_companies))

            # ----- UNMAPPED audit -----
            unmapped_leads = await conn.fetch(
                f"SELECT segment, count(*) AS n FROM leads "
                f"WHERE segment IS NOT NULL AND segment NOT IN {CANONICAL_IN_SQL} "
                f"GROUP BY segment ORDER BY n DESC"
            )
            unmapped_companies = await conn.fetch(
                f"SELECT primary_segment AS seg, count(*) AS n FROM companies "
                f"WHERE primary_segment IS NOT NULL "
                f"AND primary_segment NOT IN {CANONICAL_IN_SQL} "
                f"GROUP BY primary_segment ORDER BY n DESC"
            )

            print("\n[UNMAPPED] leads.segment values needing manual review:")
            if unmapped_leads:
                for r in unmapped_leads:
                    print(f"  {r['segment']:<36} {r['n']:>6}")
            else:
                print("  (none — all rows mapped to canonical 8 keys ✅)")

            print("\n[UNMAPPED] companies.primary_segment values:")
            if unmapped_companies:
                for r in unmapped_companies:
                    print(f"  {r['seg']:<36} {r['n']:>6}")
            else:
                print("  (none ✅)")

            print("\n" + "=" * 60)
            print("ROLLBACK — no changes committed.")
            print("=" * 60)
        finally:
            # ALWAYS rollback — this is a dry-run preview.
            await tx.rollback()
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
