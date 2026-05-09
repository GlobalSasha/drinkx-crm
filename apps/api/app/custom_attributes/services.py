"""Custom Attributes domain services — Sprint 2.4 G3.

Definitions live workspace-scoped; values are per-lead. The service is
strict about kind/value alignment so the polymorphic columns on
`lead_custom_values` stay consistent.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.custom_attributes import repositories as repo
from app.custom_attributes.models import (
    ATTRIBUTE_KINDS,
    CustomAttributeDefinition,
    LeadCustomValue,
)


# `key` must be machine-readable: lowercase letters, digits, and
# underscores. Surfaces a clear 400 instead of letting weird characters
# leak into URL paths or import column headers later.
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# ---------------------------------------------------------------------------
# Custom exceptions — router maps to HTTP
# ---------------------------------------------------------------------------

class DefinitionNotFound(Exception):
    """404 — wrong id, or cross-workspace lookup."""


class InvalidKind(Exception):
    """400 — `kind` not in ATTRIBUTE_KINDS."""


class InvalidKey(Exception):
    """400 — key doesn't match _KEY_RE."""


class DuplicateKey(Exception):
    """409 — workspace already has a definition with this key."""


class InvalidValueForKind(Exception):
    """400 — caller sent value_number for a kind='text' definition,
    or vice versa. We refuse instead of silently picking a column."""


class MissingOptions(Exception):
    """400 — kind='select' without options_json is meaningless."""


# ---------------------------------------------------------------------------
# Definition CRUD
# ---------------------------------------------------------------------------

async def list_definitions(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> list[CustomAttributeDefinition]:
    return await repo.list_definitions(db, workspace_id=workspace_id)


async def create_definition(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    key: str,
    label: str,
    kind: str,
    options_json: list[dict] | None,
    is_required: bool,
) -> CustomAttributeDefinition:
    """Validate + insert. Caller commits."""
    if kind not in ATTRIBUTE_KINDS:
        raise InvalidKind(kind)

    key_norm = key.strip().lower()
    if not _KEY_RE.match(key_norm):
        raise InvalidKey(key)

    if kind == "select" and not options_json:
        raise MissingOptions("kind='select' requires options_json")

    existing = await repo.get_by_key(
        db, workspace_id=workspace_id, key=key_norm
    )
    if existing is not None:
        raise DuplicateKey(key_norm)

    position = await repo.next_position(db, workspace_id=workspace_id)

    return await repo.create_definition(
        db,
        workspace_id=workspace_id,
        key=key_norm,
        label=label.strip(),
        kind=kind,
        options_json=options_json,
        is_required=is_required,
        position=position,
    )


async def update_definition(
    db: AsyncSession,
    *,
    definition_id: uuid.UUID,
    workspace_id: uuid.UUID,
    label: str | None = None,
    options_json: list[dict] | None = None,
    is_required: bool | None = None,
    position: int | None = None,
) -> CustomAttributeDefinition:
    definition = await repo.get_definition(
        db, definition_id=definition_id, workspace_id=workspace_id
    )
    if definition is None:
        raise DefinitionNotFound(str(definition_id))

    # If caller sends options_json for a non-select kind, ignore — same
    # idea as the dropped fields on PATCH /leads. Frontend may bulk-PATCH
    # the whole object back, no need to reject.
    if definition.kind != "select" and options_json is not None:
        options_json = None

    return await repo.update_definition(
        db,
        definition=definition,
        label=label.strip() if label is not None else None,
        options_json=options_json,
        is_required=is_required,
        position=position,
    )


async def delete_definition(
    db: AsyncSession,
    *,
    definition_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Drop the definition + cascade-delete all `lead_custom_values`
    rows that reference it (FK ON DELETE CASCADE handles that at the
    DB layer). Caller commits."""
    definition = await repo.get_definition(
        db, definition_id=definition_id, workspace_id=workspace_id
    )
    if definition is None:
        raise DefinitionNotFound(str(definition_id))

    await repo.delete_definition(db, definition=definition)


# ---------------------------------------------------------------------------
# Value upsert
# ---------------------------------------------------------------------------

async def upsert_value(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    definition_id: uuid.UUID,
    value_text: str | None = None,
    value_number: float | None = None,
    value_date: date | None = None,
) -> LeadCustomValue:
    """Set the value of one custom field on one lead.

    Dispatch:
      - kind='text'   → value_text required (non-null)
      - kind='number' → value_number required
      - kind='date'   → value_date required
      - kind='select' → value_text required + must be in options_json

    Mismatched arguments raise InvalidValueForKind. Passing all three
    as None is a delete-equivalent — it clears the value column. The
    caller may also want to call delete_value() instead; both are
    legal.
    """
    definition = await repo.get_definition(
        db, definition_id=definition_id, workspace_id=workspace_id
    )
    if definition is None:
        raise DefinitionNotFound(str(definition_id))

    kind = definition.kind
    text: str | None = None
    number: float | None = None
    dt: date | None = None

    if kind == "text":
        if value_number is not None or value_date is not None:
            raise InvalidValueForKind(
                "kind='text' accepts only value_text"
            )
        text = value_text
    elif kind == "number":
        if value_text is not None or value_date is not None:
            raise InvalidValueForKind(
                "kind='number' accepts only value_number"
            )
        number = value_number
    elif kind == "date":
        if value_text is not None or value_number is not None:
            raise InvalidValueForKind(
                "kind='date' accepts only value_date"
            )
        dt = value_date
    elif kind == "select":
        if value_number is not None or value_date is not None:
            raise InvalidValueForKind(
                "kind='select' accepts only value_text"
            )
        if value_text is not None:
            options = definition.options_json or []
            allowed = {opt.get("value") for opt in options}
            if value_text not in allowed:
                raise InvalidValueForKind(
                    f"value '{value_text}' not in options for {definition.key}"
                )
        text = value_text
    else:
        # Defensive — should never trip because create_definition
        # validates. Surface a clear error if a stale row sneaks in.
        raise InvalidKind(kind)

    return await repo.upsert_value(
        db,
        lead_id=lead_id,
        definition_id=definition_id,
        value_text=text,
        value_number=number,
        value_date=dt,
    )
