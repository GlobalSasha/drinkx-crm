"""Custom Attributes Pydantic schemas — Sprint 2.4 G3."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirror models.ATTRIBUTE_KINDS — duplicated here so Pydantic
# Literal validation gives a clean 422 message at the API boundary
# instead of bouncing through service code.
AttributeKind = Literal["text", "number", "date", "select"]


class AttributeOption(BaseModel):
    """One choice for kind='select'. `value` is what's stored on the
    LeadCustomValue.value_text column; `label` is the UI rendering."""
    value: str
    label: str


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------

class CustomAttributeDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    label: str
    kind: AttributeKind
    options_json: list[AttributeOption] | None = None
    is_required: bool
    position: int


class CustomAttributeDefinitionCreateIn(BaseModel):
    """POST body. `key` is immutable post-create; the service rejects
    `key` changes via PATCH. `position` is auto-assigned (last) if
    omitted."""
    key: str = Field(..., min_length=1, max_length=60)
    label: str = Field(..., min_length=1, max_length=120)
    kind: AttributeKind
    options_json: list[AttributeOption] | None = None
    is_required: bool = False


class CustomAttributeDefinitionUpdateIn(BaseModel):
    """PATCH body. Note `key` is intentionally absent — renaming the
    key would orphan existing values, so it's not in the update
    schema. The kind is also locked post-create (changing kind would
    invalidate already-populated value columns)."""
    label: str | None = Field(None, min_length=1, max_length=120)
    options_json: list[AttributeOption] | None = None
    is_required: bool | None = None
    position: int | None = None


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

class LeadCustomValueOut(BaseModel):
    """One value as the LeadCard would render it. The polymorphic
    columns are flattened into a single `value` field — frontend
    doesn't need to know about the storage shape.

    `value` is `Any`-shaped: str for text/select, float for number,
    ISO-8601 date string for date."""
    model_config = ConfigDict(from_attributes=False)

    definition_id: uuid.UUID
    key: str
    kind: AttributeKind
    value: str | float | date | None = None


class LeadCustomValueUpsertIn(BaseModel):
    """Set one value on one lead. Send the matching field for the
    definition's kind; the service ignores the others."""
    value_text: str | None = None
    value_number: float | None = None
    value_date: date | None = None


# ---------------------------------------------------------------------------
# Sprint 2.6 G4 — flat list + string-value upsert + reorder
# ---------------------------------------------------------------------------

class LeadAttributeOut(BaseModel):
    """Merged definition + value row used by the LeadCard custom-fields
    section. `value` is `null` when the manager hasn't set one yet;
    otherwise it's a string for text/select, float for number, ISO
    date string for date."""
    definition_id: uuid.UUID
    key: str
    label: str
    kind: AttributeKind
    options_json: list[AttributeOption] | None = None
    is_required: bool
    position: int
    value: str | float | date | None = None


class LeadAttributeUpsertIn(BaseModel):
    """PATCH /api/leads/{id}/attributes body. Frontend sends the input
    value as a string (from a `<input>` element); the backend parses
    against the definition's `kind`. Empty / null clears the value."""
    definition_id: uuid.UUID
    value: str | None = None


class CustomAttributeReorderIn(BaseModel):
    """PATCH /api/custom-attributes/reorder body. Caller sends every
    definition id in the desired display order; the service writes
    `position = index` on each row. Refuses partial reorders — every
    id must belong to the caller's workspace."""
    ordered_ids: list[uuid.UUID] = Field(..., min_length=1)
