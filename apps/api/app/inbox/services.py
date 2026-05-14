"""Inbox service layer — list / count / confirm / dismiss.

`confirm_item` is the human-in-the-loop entry point (ADR-007). It turns
a pending InboxItem into one of:
  - match_lead   — attach the email to an existing Lead as an Activity
  - create_lead  — create a new Lead in the pool + attach the email
  - add_contact  — add a Contact to an existing Lead (and the email)

Per ADR-019 every Activity created here is lead-scoped; user_id records
which manager confirmed the action (audit trail), not visibility.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.audit.audit import log as audit_log
from app.contacts.models import Contact
from app.inbox.models import InboxItem
from app.leads.models import Lead

log = structlog.get_logger()


class InboxItemNotFound(Exception):
    pass


class InboxItemBadRequest(Exception):
    pass


VALID_ACTIONS = {"match_lead", "create_lead", "add_contact"}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_inbox(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str = "pending",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[InboxItem], int]:
    """Paginated InboxItem list, scoped to workspace + status."""
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    offset = (page - 1) * page_size

    base = select(InboxItem).where(InboxItem.workspace_id == workspace_id)
    if status:
        base = base.where(InboxItem.status == status)

    total_res = await session.execute(
        select(func.count())
        .select_from(InboxItem)
        .where(InboxItem.workspace_id == workspace_id)
        .where(InboxItem.status == status if status else True)
    )
    total = int(total_res.scalar_one() or 0)

    rows_res = await session.execute(
        base.order_by(InboxItem.received_at.desc()).offset(offset).limit(page_size)
    )
    items = list(rows_res.scalars())
    return items, total


async def count_pending(session: AsyncSession, *, workspace_id: UUID) -> int:
    """How many pending items in this workspace — for the sidebar badge."""
    res = await session.execute(
        select(func.count())
        .select_from(InboxItem)
        .where(InboxItem.workspace_id == workspace_id)
        .where(InboxItem.status == "pending")
    )
    return int(res.scalar_one() or 0)


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

async def _load_item(
    session: AsyncSession, *, item_id: UUID, workspace_id: UUID
) -> InboxItem:
    res = await session.execute(
        select(InboxItem)
        .where(InboxItem.id == item_id)
        .where(InboxItem.workspace_id == workspace_id)
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise InboxItemNotFound(str(item_id))
    return item


def _activity_kwargs_from_item(
    item: InboxItem, *, lead_id: UUID, user_id: UUID | None
) -> dict[str, Any]:
    """Shared Activity payload — keep this in sync with processor.process_message."""
    to_id = (",".join(item.to_emails or []))[:300] if item.to_emails else None
    return {
        "lead_id": lead_id,
        "user_id": user_id,
        "type": "email",
        "channel": "gmail",
        "direction": item.direction,
        "subject": item.subject or None,
        "body": item.body_preview or None,
        "gmail_message_id": item.gmail_message_id,
        "from_identifier": item.from_email or None,
        "to_identifier": to_id,
        "payload_json": {
            "match_type": "manual_confirm",
            "received_at": item.received_at.isoformat() if item.received_at else None,
            "inbox_item_id": str(item.id),
        },
    }


async def confirm_item(
    session: AsyncSession,
    *,
    item_id: UUID,
    user_id: UUID,
    workspace_id: UUID,
    action: str,
    lead_id: UUID | None = None,
    company_name: str | None = None,
    contact_name: str | None = None,
) -> InboxItem:
    """Resolve a pending InboxItem via the human-confirmed `action`."""
    if action not in VALID_ACTIONS:
        raise InboxItemBadRequest(f"unknown action: {action}")

    item = await _load_item(session, item_id=item_id, workspace_id=workspace_id)

    if action == "match_lead":
        if lead_id is None:
            raise InboxItemBadRequest("lead_id is required for match_lead")
        await _verify_lead_in_workspace(
            session, lead_id=lead_id, workspace_id=workspace_id
        )
        session.add(
            Activity(**_activity_kwargs_from_item(item, lead_id=lead_id, user_id=user_id))
        )
        item.status = "matched"
        await audit_log(
            session,
            action="inbox.match_lead",
            workspace_id=workspace_id,
            user_id=user_id,
            entity_type="inbox_item",
            entity_id=item.id,
            delta={"lead_id": str(lead_id), "gmail_message_id": item.gmail_message_id},
        )

    elif action == "create_lead":
        from app.pipelines import repositories as pipelines_repo

        company = (company_name or "").strip()
        if not company:
            # Fall back to from_email as the lead title — never refuse the
            # confirmation just because the manager didn't fill it in.
            company = item.from_email or "Unknown"

        first = await pipelines_repo.get_default_first_stage(session, workspace_id)
        pipeline_id, stage_id = first if first is not None else (None, None)

        new_lead = Lead(
            workspace_id=workspace_id,
            pipeline_id=pipeline_id,
            stage_id=stage_id,
            company_name=company[:255],
            email=item.from_email or None,
            source="inbox:gmail",
            assignment_status="pool",
            tags_json=[],
        )
        session.add(new_lead)
        await session.flush()  # need new_lead.id

        session.add(
            Activity(**_activity_kwargs_from_item(item, lead_id=new_lead.id, user_id=user_id))
        )
        item.status = "created_lead"
        await audit_log(
            session,
            action="inbox.create_lead",
            workspace_id=workspace_id,
            user_id=user_id,
            entity_type="inbox_item",
            entity_id=item.id,
            delta={
                "lead_id": str(new_lead.id),
                "company_name": new_lead.company_name,
                "gmail_message_id": item.gmail_message_id,
            },
        )

    elif action == "add_contact":
        if lead_id is None:
            raise InboxItemBadRequest("lead_id is required for add_contact")
        await _verify_lead_in_workspace(
            session, lead_id=lead_id, workspace_id=workspace_id
        )
        contact = Contact(
            lead_id=lead_id,
            workspace_id=workspace_id,
            name=(contact_name or item.from_email or "Unknown")[:120],
            email=item.from_email or None,
            source="gmail",
        )
        session.add(contact)
        session.add(
            Activity(**_activity_kwargs_from_item(item, lead_id=lead_id, user_id=user_id))
        )
        item.status = "matched"
        await audit_log(
            session,
            action="inbox.add_contact",
            workspace_id=workspace_id,
            user_id=user_id,
            entity_type="inbox_item",
            entity_id=item.id,
            delta={
                "lead_id": str(lead_id),
                "contact_name": contact.name,
                "gmail_message_id": item.gmail_message_id,
            },
        )

    await session.commit()
    await session.refresh(item)
    return item


async def dismiss_item(
    session: AsyncSession,
    *,
    item_id: UUID,
    user_id: UUID,
    workspace_id: UUID,
) -> InboxItem:
    item = await _load_item(session, item_id=item_id, workspace_id=workspace_id)
    item.status = "dismissed"
    await audit_log(
        session,
        action="inbox.dismiss",
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type="inbox_item",
        entity_id=item.id,
        delta={"gmail_message_id": item.gmail_message_id},
    )
    await session.commit()
    await session.refresh(item)
    return item


async def _verify_lead_in_workspace(
    session: AsyncSession, *, lead_id: UUID, workspace_id: UUID
) -> None:
    res = await session.execute(
        select(Lead.id)
        .where(Lead.id == lead_id)
        .where(Lead.workspace_id == workspace_id)
    )
    if res.scalar_one_or_none() is None:
        raise InboxItemNotFound(f"lead {lead_id} not in workspace")
