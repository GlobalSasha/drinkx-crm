"""API shapes for «Голос клиентов». Worker payloads are lenient on purpose
(Optional + defaults): a malformed tag is dropped, never a 422 for the batch."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Worker side (/worker/v1/insights) ─────────────────────────────────────

class CategoryOut(BaseModel):
    key: str
    group: str
    label: str


class PendingComment(BaseModel):
    activity_id: uuid.UUID
    text: str  # phones and e-mails already cut out


class PendingOut(BaseModel):
    categories: list[CategoryOut]  # the only keys a tag may use
    comments: list[PendingComment]


class TagIn(BaseModel):
    category: str = ""
    quote: str = ""
    competitor: str | None = None


class CommentTagsIn(BaseModel):
    activity_id: uuid.UUID
    tags: list[TagIn] = Field(default_factory=list)
    failed: bool = False  # the worker could not process this comment


class IngestIn(BaseModel):
    items: list[CommentTagsIn] = Field(default_factory=list, max_length=200)


class IngestOut(BaseModel):
    accepted: int  # tags stored
    dropped: int  # tags rejected (unknown category, quote not in the comment)
    scanned: int  # comments marked as looked at
    failed: int  # comments marked failed (will be retried)


# ── Head/admin side (/company/voice) ────────────────────────────────────────

class VoiceQuote(BaseModel):
    lead_id: uuid.UUID
    company_name: str
    author: str | None
    quote: str
    at: datetime


class VoiceItem(BaseModel):
    key: str  # category key, or "competitor:<name>"
    label: str
    leads: int  # distinct leads in the period
    previous: int  # the same for the period before
    quotes: list[VoiceQuote]  # newest first, up to 5


class VoiceGroup(BaseModel):
    group: str
    label: str
    items: list[VoiceItem]  # most leads first


class LostReasonCount(BaseModel):
    reason: str
    count: int


class CompanyVoiceOut(BaseModel):
    period: str  # "week" | "month"
    days: int
    groups: list[VoiceGroup]  # only groups with something in them
    lost_reasons: list[LostReasonCount]  # from the «Сделка проиграна» window, no AI
    comments_total: int  # manager comments in the period
    comments_pending: int  # of them, not looked at by the AI yet
    last_scan_at: datetime | None
