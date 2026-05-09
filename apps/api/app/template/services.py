"""Message Templates domain services — Sprint 2.4 G4.

Three operations: list / create / update / delete. All workspace-
scoped. The service is responsible for:
  - validating channel against VALID_CHANNELS
  - detecting (workspace, name, channel) duplicates and raising
    DuplicateTemplate so the router can map to a structured 409
    (same shape as Sprint 2.3's PipelineHasLeads)
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.template import repositories as repo
from app.template.models import VALID_CHANNELS, MessageTemplate


# ---------------------------------------------------------------------------
# Custom exceptions — router maps to HTTP
# ---------------------------------------------------------------------------

class TemplateNotFound(Exception):
    """404 — wrong id, or cross-workspace lookup."""


class InvalidChannel(Exception):
    """400 — channel string not in VALID_CHANNELS."""


class DuplicateTemplate(Exception):
    """409 — (workspace, name, channel) already taken. Carries the
    target name + channel for the structured 409 detail."""

    def __init__(self, name: str, channel: str) -> None:
        super().__init__(f"{name!r} on {channel!r}")
        self.name = name
        self.channel = channel


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_templates(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    channel: str | None = None,
) -> list[MessageTemplate]:
    if channel is not None and channel not in VALID_CHANNELS:
        raise InvalidChannel(channel)
    return await repo.list_for_workspace(
        db, workspace_id=workspace_id, channel=channel
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

async def create_template(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID,
    name: str,
    channel: str,
    category: str | None,
    text: str,
) -> MessageTemplate:
    """Validate + duplicate-check + insert. Caller commits."""
    if channel not in VALID_CHANNELS:
        raise InvalidChannel(channel)

    name_norm = name.strip()
    existing = await repo.get_by_name_and_channel(
        db, workspace_id=workspace_id, name=name_norm, channel=channel
    )
    if existing is not None:
        raise DuplicateTemplate(name_norm, channel)

    return await repo.create(
        db,
        workspace_id=workspace_id,
        name=name_norm,
        channel=channel,
        category=category.strip() if category else None,
        text=text,
        created_by=created_by,
    )


async def update_template(
    db: AsyncSession,
    *,
    template_id: uuid.UUID,
    workspace_id: uuid.UUID,
    name: str | None = None,
    channel: str | None = None,
    category: str | None = None,
    text: str | None = None,
    category_set: bool = False,
) -> MessageTemplate:
    """Patch with duplicate-aware rename guard. If name OR channel
    changes, check that the new (workspace, name, channel) tuple
    isn't taken by a DIFFERENT row. Caller commits."""
    if channel is not None and channel not in VALID_CHANNELS:
        raise InvalidChannel(channel)

    template = await repo.get_by_id(
        db, template_id=template_id, workspace_id=workspace_id
    )
    if template is None:
        raise TemplateNotFound(str(template_id))

    target_name = name.strip() if name is not None else template.name
    target_channel = channel if channel is not None else template.channel

    if target_name != template.name or target_channel != template.channel:
        clash = await repo.get_by_name_and_channel(
            db,
            workspace_id=workspace_id,
            name=target_name,
            channel=target_channel,
        )
        if clash is not None and clash.id != template.id:
            raise DuplicateTemplate(target_name, target_channel)

    return await repo.update(
        db,
        template=template,
        name=name.strip() if name is not None else None,
        channel=channel,
        category=(
            category.strip() if (category_set and category) else category
        ),
        text=text,
        category_set=category_set,
    )


async def delete_template(
    db: AsyncSession,
    *,
    template_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    template = await repo.get_by_id(
        db, template_id=template_id, workspace_id=workspace_id
    )
    if template is None:
        raise TemplateNotFound(str(template_id))
    await repo.delete(db, template=template)
