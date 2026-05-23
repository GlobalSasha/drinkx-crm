"""base_update services: matching, auto-apply, resolution apply.

Only the matching slice is implemented here so far; auto-apply (Task 9)
and resolution applier (Task 10) come next.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.companies.utils import normalize_company_name


@dataclass
class CompanyMatch:
    action: str  # "create" | "update" | "ambiguous"
    company_id: Any = None  # uuid.UUID at runtime; Any keeps the pure tests cheap
    candidates: list[dict] = field(default_factory=list)  # [{id, name}] for ambiguous (#1)


def _match_from_rows(name: str, rows: list[Any]) -> CompanyMatch:
    """Pure: given a name and the active-company rows already filtered by normalized key,
    decide create / update / ambiguous. Rows must expose `.id` and `.name`.
    """
    if not (name or "").strip():
        return CompanyMatch(action="create")
    if not rows:
        return CompanyMatch(action="create")
    if len(rows) == 1:
        return CompanyMatch(action="update", company_id=rows[0].id)
    return CompanyMatch(
        action="ambiguous",
        candidates=[{"id": str(r.id), "name": r.name} for r in rows],
    )


async def match_company(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str
) -> CompanyMatch:
    """Look up active companies whose normalized_name equals the normalized
    form of `name`, then classify via the pure helper."""
    key = normalize_company_name(name or "")
    if not key:
        return CompanyMatch(action="create")
    rows = (
        await db.execute(
            select(Company).where(
                Company.workspace_id == workspace_id,
                Company.normalized_name == key,
                Company.archived_at.is_(None),
            )
        )
    ).scalars().all()
    return _match_from_rows(name, list(rows))
