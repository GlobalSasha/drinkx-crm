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


# ── «Сводка за 5 дней» ──────────────────────────────────────────────────────

class DigestComment(BaseModel):
    at: datetime
    author: str | None
    text: str  # phones and e-mails already cut out


class DigestSourceLead(BaseModel):
    lead_id: uuid.UUID
    company_name: str
    stage: str | None
    city: str | None
    comments: list[DigestComment]  # oldest first


class DigestSourceOut(BaseModel):
    period_from: datetime
    period_to: datetime
    sections: list[CategoryOut]  # the only section keys a digest may use
    leads: list[DigestSourceLead]


class DigestItemIn(BaseModel):
    client: str = ""  # short client label for the left column, e.g. «Гуру кофе (СПб)»
    text: str = ""
    lead_ids: list[uuid.UUID] = Field(default_factory=list)


class DigestSectionIn(BaseModel):
    key: str = ""
    items: list[DigestItemIn] = Field(default_factory=list, max_length=30)


class DigestIn(BaseModel):
    period_from: datetime
    period_to: datetime
    sections: list[DigestSectionIn] = Field(default_factory=list, max_length=10)


class DigestInOut(BaseModel):
    accepted: int  # lines stored
    dropped: int  # lines rejected (unknown section, empty, lead not in the period)


class DigestLead(BaseModel):
    id: uuid.UUID
    company_name: str


class DigestItemOut(BaseModel):
    client: str | None  # None in digests written before the label existed
    text: str
    leads: list[DigestLead]


class DigestSectionOut(BaseModel):
    key: str
    title: str
    items: list[DigestItemOut]


class DigestOut(BaseModel):
    created_at: datetime
    period_from: datetime
    period_to: datetime
    comments: int  # manager comments in the period
    leads: int  # distinct leads they are on
    sections: list[DigestSectionOut]  # only non-empty, fixed order


class NewLeadOut(BaseModel):
    id: uuid.UUID
    company_name: str
    city: str | None
    source: str | None
    manager: str | None
    created_at: datetime


class CompanyDigestOut(BaseModel):
    digest: DigestOut | None  # None until the worker sends the first one
    stale: bool  # no fresh digest in the last DIGEST_STALE_HOURS
    new_leads_from: datetime
    new_leads: list[NewLeadOut]  # straight from the base, newest first, no AI
