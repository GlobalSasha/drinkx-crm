"""One-shot backfill for Sprint 3.3 Companies.

Runs AFTER alembic migration 0023_companies. NOT itself an alembic
migration. Dedup by `normalize_company_name` (not raw `company_name`).

Sequence:
  1. For each (workspace_id, normalized_name) — insert one `companies`
     row, keep the original casing from the first occurrence.
  2. Link `leads.company_id` via the (workspace_id, company_name)
     mapping.
  3. Backfill `contacts.workspace_id` from the parent lead.
  4. Backfill `contacts.company_id` from the parent lead.
  5. Print a summary + merge candidates (active rows that still share
     a normalized_name — none expected after this script).
  6. Assert no `contacts.workspace_id IS NULL` rows remain. Operator
     then runs migration 0024 to flip the column to NOT NULL.

Usage:
    DATABASE_URL=postgresql+asyncpg://drinkx:...@host:5432/drinkx_crm \\
        python3 scripts/backfill_companies.py            # dry-run
        python3 scripts/backfill_companies.py --apply    # actually write
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.companies.utils import extract_domain, normalize_company_name  # noqa: E402


async def main(apply_changes: bool) -> int:
    import asyncpg  # lazy — keeps unit tests importable

    db_url = os.environ.get("DATABASE_URL", "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    if not db_url:
        print("✗ DATABASE_URL not set", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(db_url)
    try:
        # ----- Step 1: distinct (workspace_id, company_name) → companies -----
        # Also keep each lead's id so step 2 can write back without a
        # second SELECT + Postgres-side re-normalization (the old SQL
        # regex duplicated the Python `_ORG_FORMS` table and would drift).
        rows = await conn.fetch(
            """
            SELECT id, workspace_id, company_name, segment, website, city
            FROM leads
            WHERE company_name IS NOT NULL
              AND length(trim(company_name)) > 0
              AND company_id IS NULL
            """
        )
        print(f"Step 1 — {len(rows)} leads need company linkage")

        seen: dict[tuple[str, str], str] = {}  # (wid, normalized) -> company_id
        lead_company_pairs: list[tuple[Any, Any]] = []  # (lead_id, company_id)
        companies_created = 0
        for r in rows:
            normalized = normalize_company_name(r["company_name"])
            key = (str(r["workspace_id"]), normalized)
            if key not in seen:
                if apply_changes:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO companies
                          (id, workspace_id, name, normalized_name, domain,
                           primary_segment, city, website, created_at, updated_at)
                        VALUES
                          (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, now(), now())
                        RETURNING id
                        """,
                        r["workspace_id"],
                        r["company_name"],
                        normalized,
                        extract_domain(r["website"]),
                        r["segment"],
                        r["city"],
                        r["website"],
                    )
                    seen[key] = row["id"]
                else:
                    # Dry-run sentinel — never sent to DB. Tuple in
                    # `lead_company_pairs` below uses this verbatim, but
                    # the apply-branch is what executes the UPDATE.
                    seen[key] = f"<dry-run-uuid-{len(seen)}>"
                companies_created += 1
            lead_company_pairs.append((r["id"], seen[key]))

        # ----- Step 2: link leads via one bulk UPDATE using unnest() -----
        # Drives the mapping straight from in-memory pairs — no second
        # SQL normalisation, no temp table. asyncpg ships the two
        # arrays as parameters in a single round-trip.
        leads_linked = 0
        if apply_changes and lead_company_pairs:
            lead_ids = [pair[0] for pair in lead_company_pairs]
            company_ids = [pair[1] for pair in lead_company_pairs]
            result = await conn.execute(
                """
                UPDATE leads l
                SET company_id = u.company_id, updated_at = now()
                FROM unnest($1::uuid[], $2::uuid[]) AS u(lead_id, company_id)
                WHERE l.id = u.lead_id AND l.company_id IS NULL
                """,
                lead_ids,
                company_ids,
            )
            # asyncpg returns 'UPDATE N'
            leads_linked = int(result.split()[-1]) if result.startswith("UPDATE") else 0
        else:
            # Dry-run: exact count of what apply would touch.
            leads_linked = len(lead_company_pairs)

        # ----- Step 3: contacts.workspace_id from parent lead -----
        contacts_workspace_filled = 0
        if apply_changes:
            result = await conn.execute(
                """
                UPDATE contacts ct
                SET workspace_id = l.workspace_id, updated_at = now()
                FROM leads l
                WHERE ct.lead_id = l.id AND ct.workspace_id IS NULL
                """
            )
            contacts_workspace_filled = (
                int(result.split()[-1]) if result.startswith("UPDATE") else 0
            )
        else:
            contacts_workspace_filled = (
                await conn.fetchval(
                    "SELECT count(*) FROM contacts WHERE workspace_id IS NULL"
                )
                or 0
            )

        # ----- Step 4: contacts.company_id from parent lead -----
        contacts_company_filled = 0
        if apply_changes:
            result = await conn.execute(
                """
                UPDATE contacts ct
                SET company_id = l.company_id, updated_at = now()
                FROM leads l
                WHERE ct.lead_id = l.id
                  AND l.company_id IS NOT NULL
                  AND ct.company_id IS NULL
                """
            )
            contacts_company_filled = (
                int(result.split()[-1]) if result.startswith("UPDATE") else 0
            )
        else:
            contacts_company_filled = (
                await conn.fetchval(
                    """
                    SELECT count(*)
                    FROM contacts ct
                    JOIN leads l ON l.id = ct.lead_id
                    WHERE ct.company_id IS NULL
                    """
                )
                or 0
            )

        # ----- Step 5: report -----
        merge_candidates = await conn.fetch(
            """
            SELECT workspace_id, normalized_name, count(*) AS dup_count,
                   array_agg(id::text) AS ids, array_agg(name) AS names
            FROM companies
            WHERE is_archived = false
            GROUP BY workspace_id, normalized_name
            HAVING count(*) > 1
            """
        )

        print()
        print("=" * 60)
        print(f"  Mode: {'APPLY' if apply_changes else 'DRY-RUN'}")
        print("=" * 60)
        print(f"  Companies created       : {companies_created}")
        print(f"  Leads linked            : {leads_linked}")
        print(f"  contacts.workspace_id   : {contacts_workspace_filled}")
        print(f"  contacts.company_id     : {contacts_company_filled}")
        print(f"  Merge candidates        : {len(merge_candidates)}")
        for m in merge_candidates:
            print(f"    - workspace {m['workspace_id']} normalized={m['normalized_name']!r} count={m['dup_count']} ids={m['ids']}")
        print("=" * 60)

        # ----- Step 6: acceptance check -----
        if apply_changes:
            remaining_null = (
                await conn.fetchval(
                    "SELECT count(*) FROM contacts WHERE workspace_id IS NULL"
                )
                or 0
            )
            if remaining_null != 0:
                print(
                    f"✗ Acceptance FAIL: contacts WHERE workspace_id IS NULL = {remaining_null}",
                    file=sys.stderr,
                )
                return 3
            remaining_unlinked = (
                await conn.fetchval(
                    """
                    SELECT count(*) FROM leads
                    WHERE company_name IS NOT NULL
                      AND length(trim(company_name)) > 0
                      AND company_id IS NULL
                    """
                )
                or 0
            )
            if remaining_unlinked != 0:
                print(
                    f"⚠ {remaining_unlinked} leads still have no company_id (likely whitespace-only names).",
                    file=sys.stderr,
                )
            print("✓ Acceptance OK — operator may now run migration 0024.")
        else:
            print("dry-run only — no rows changed. Re-run with --apply to write.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Default is dry-run.",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(main(apply_changes=args.apply)))
