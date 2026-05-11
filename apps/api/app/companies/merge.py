"""Merge logic — folds a source company into a target. Source ends up
archived; leads + contacts re-point at target. Historical lead snapshots
(closed/won/lost or archived) keep their original `company_name`.

The spec's `leads.is_archived = false` filter is implemented here as
`leads.archived_at IS NULL` (the real column; see Phase 0 feasibility).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import log as audit_log
from app.companies.models import Company
from app.companies.repositories import get_by_id


class InnConflict(Exception):
    """Source and target have different non-null INNs and `force` is
    False. Surface as 409 with `code='inn_conflict'`."""

    def __init__(self, source_inn: str, target_inn: str):
        self.source_inn = source_inn
        self.target_inn = target_inn


class MergeNotPossible(Exception):
    """Either source or target missing, or pointing into a different
    workspace. Surface as 404."""

    def __init__(self, message: str):
        self.message = message


async def merge_into(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID | None,
    source_id: UUID,
    target_id: UUID,
    force: bool = False,
) -> Company:
    if source_id == target_id:
        raise MergeNotPossible("source and target are the same")

    source = await get_by_id(db, workspace_id=workspace_id, company_id=source_id)
    target = await get_by_id(db, workspace_id=workspace_id, company_id=target_id)
    if source is None or target is None:
        raise MergeNotPossible("source or target not found")

    # 1. INN conflict guard
    if (
        source.inn
        and target.inn
        and source.inn != target.inn
        and not force
    ):
        raise InnConflict(source.inn, target.inn)

    # 2. If target has no INN and source does, transfer it.
    if not target.inn and source.inn:
        target.inn = source.inn
        # KPP is functionally tied to INN — move it along.
        if not target.kpp and source.kpp:
            target.kpp = source.kpp

    # 3. Move leads: only ACTIVE non-terminal rows inherit the new
    #    company_name; closed (won/lost) and archived rows keep the
    #    historical snapshot.
    await db.execute(
        text(
            "UPDATE leads l "
            "SET company_id   = :target_id, "
            "    company_name = CASE "
            "        WHEN l.archived_at IS NULL "
            "         AND NOT EXISTS ( "
            "             SELECT 1 FROM stages s "
            "             WHERE s.id = l.stage_id "
            "               AND (s.is_won = true OR s.is_lost = true) "
            "         ) "
            "        THEN :target_name "
            "        ELSE l.company_name "
            "    END, "
            "    updated_at = now() "
            "WHERE l.company_id = :source_id"
        ),
        {
            "source_id": source_id,
            "target_id": target_id,
            "target_name": target.name,
        },
    )

    # 4. Move contacts.
    await db.execute(
        text(
            "UPDATE contacts SET company_id = :target_id, updated_at = now() "
            "WHERE company_id = :source_id"
        ),
        {"source_id": source_id, "target_id": target_id},
    )

    # 5. Archive source.
    source.is_archived = True
    source.archived_at = datetime.now(tz=timezone.utc)

    # 6. Audit.
    await audit_log(
        db,
        action="company.merge",
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type="company",
        entity_id=target_id,
        delta={"source_id": str(source_id), "target_id": str(target_id)},
    )

    await db.flush()
    return target
