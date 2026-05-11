"""Global search SQL — fork on query length.

`len(q) < 3` → `_search_ilike`: exact `ILIKE '%q%'` only over name +
INN/email/phone. No `similarity()`, no `%` trigram operator. Avoids
the noise + perf cliff of trigram on 1–2 char queries.

`len(q) >= 3` → `_search_trgm`: full union with `similarity()` + the
`%` operator, ranked DESC.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _search_ilike(
    db: AsyncSession, *, workspace_id: UUID, q: str, limit: int
) -> list[dict[str, Any]]:
    """Short query (1-2 chars): exact ILIKE only, no fuzzy."""
    pattern = f"%{q}%"
    rows = (
        await db.execute(
            text(
                """
                SELECT 'company' AS type, c.id::text AS id,
                  c.name AS title,
                  COALESCE('ИНН: ' || c.inn, c.city, '') AS subtitle,
                  NULL::uuid AS lead_id,
                  '/companies/' || c.id AS url,
                  NULL::float AS rank
                FROM companies c
                WHERE c.workspace_id = :wid AND c.is_archived = false
                  AND (c.name ILIKE :pat OR c.inn ILIKE :pat OR c.email ILIKE :pat OR c.phone ILIKE :pat)
                LIMIT :lim

                UNION ALL

                SELECT 'lead' AS type, l.id::text,
                  l.company_name AS title,
                  s.name AS subtitle,
                  l.id AS lead_id,
                  '/leads/' || l.id AS url,
                  NULL::float AS rank
                FROM leads l
                LEFT JOIN stages s ON s.id = l.stage_id
                WHERE l.workspace_id = :wid
                  AND (l.company_name ILIKE :pat OR l.email ILIKE :pat OR l.phone ILIKE :pat OR l.inn ILIKE :pat)
                LIMIT :lim

                UNION ALL

                SELECT 'contact' AS type, ct.id::text,
                  ct.name AS title,
                  COALESCE(ct.email, ct.phone, '') AS subtitle,
                  ct.lead_id,
                  CASE
                    WHEN ct.lead_id    IS NOT NULL THEN '/leads/' || ct.lead_id
                    WHEN ct.company_id IS NOT NULL THEN '/companies/' || ct.company_id
                    ELSE '/contacts/' || ct.id
                  END AS url,
                  NULL::float AS rank
                FROM contacts ct
                WHERE ct.workspace_id = :wid
                  AND (ct.name ILIKE :pat OR ct.email ILIKE :pat OR ct.phone ILIKE :pat)
                LIMIT :lim
                """
            ),
            {"wid": str(workspace_id), "pat": pattern, "lim": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _search_trgm(
    db: AsyncSession, *, workspace_id: UUID, q: str, limit: int
) -> list[dict[str, Any]]:
    """≥3 chars: trigram similarity ranked across companies + leads +
    contacts. The CTE pre-computes `q` and `q_like` so each UNION arm
    references them once."""
    rows = (
        await db.execute(
            text(
                """
                WITH query AS (
                  SELECT CAST(:wid AS uuid) AS workspace_id,
                         trim(:q) AS q,
                         '%' || trim(:q) || '%' AS q_like
                )
                SELECT * FROM (

                  SELECT 'company' AS type, c.id::text AS id,
                    c.name AS title,
                    COALESCE('ИНН: ' || c.inn, c.city, '') AS subtitle,
                    NULL::uuid AS lead_id,
                    '/companies/' || c.id AS url,
                    GREATEST(
                      similarity(c.name, q.q),
                      similarity(COALESCE(c.inn, ''), q.q)
                    ) AS rank
                  FROM companies c, query q
                  WHERE c.workspace_id = q.workspace_id AND c.is_archived = false
                    AND (c.name % q.q OR c.inn ILIKE q.q_like OR c.website ILIKE q.q_like)

                  UNION ALL

                  SELECT 'lead' AS type, l.id::text,
                    l.company_name AS title,
                    s.name AS subtitle,
                    l.id AS lead_id,
                    '/leads/' || l.id AS url,
                    similarity(l.company_name, q.q) AS rank
                  FROM leads l
                  LEFT JOIN stages s ON s.id = l.stage_id, query q
                  WHERE l.workspace_id = q.workspace_id
                    AND (l.company_name % q.q OR l.email ILIKE q.q_like OR l.phone ILIKE q.q_like)

                  UNION ALL

                  SELECT 'contact' AS type, ct.id::text,
                    ct.name AS title,
                    COALESCE(ct.email, ct.phone, '') AS subtitle,
                    ct.lead_id,
                    CASE
                      WHEN ct.lead_id    IS NOT NULL THEN '/leads/' || ct.lead_id
                      WHEN ct.company_id IS NOT NULL THEN '/companies/' || ct.company_id
                      ELSE '/contacts/' || ct.id
                    END AS url,
                    GREATEST(
                      similarity(ct.name, q.q),
                      similarity(COALESCE(ct.email, ''), q.q),
                      similarity(COALESCE(ct.phone, ''), q.q)
                    ) AS rank
                  FROM contacts ct, query q
                  WHERE ct.workspace_id = q.workspace_id
                    AND (ct.name % q.q OR ct.email ILIKE q.q_like OR ct.phone ILIKE q.q_like)

                ) results
                ORDER BY rank DESC NULLS LAST
                LIMIT :lim
                """
            ),
            {"wid": str(workspace_id), "q": q, "lim": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def search(
    db: AsyncSession, *, workspace_id: UUID, q: str, limit: int = 20
) -> tuple[list[dict[str, Any]], str]:
    """Returns (rows, mode) — mode is 'ilike' | 'trgm' | 'empty'."""
    q = (q or "").strip()
    if not q:
        return [], "empty"
    if len(q) < 3:
        return await _search_ilike(
            db, workspace_id=workspace_id, q=q, limit=limit
        ), "ilike"
    return await _search_trgm(
        db, workspace_id=workspace_id, q=q, limit=limit
    ), "trgm"
