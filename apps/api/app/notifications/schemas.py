"""Notification API schemas — Sprint 1.5."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    title: str
    body: str
    lead_id: UUID | None
    read_at: datetime | None
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
    page: int
    page_size: int


class MarkAllReadOut(BaseModel):
    affected: int


# --- Web Push (phone notifications) ---------------------------------------

_PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com",          # Chrome / Android / Edge (via FCM)
    ".push.apple.com",             # Safari, iPhone home-screen app
    "updates.push.services.mozilla.com",  # Firefox
    ".notify.windows.com",         # legacy Edge / Windows
)


class PushConfigOut(BaseModel):
    enabled: bool
    public_key: str | None = None


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=2000)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def _known_push_service(cls, value: str) -> str:
        """The worker POSTs to this URL — accept only real push services,
        never an arbitrary (internal) address."""
        from urllib.parse import urlparse

        url = urlparse(value)
        host = (url.hostname or "").lower()
        ok_host = any(
            host == s.lstrip(".") or host.endswith(s if s.startswith(".") else "." + s)
            for s in _PUSH_HOST_SUFFIXES
        )
        if url.scheme != "https" or not ok_host:
            raise ValueError("Неизвестный сервис push-уведомлений")
        return value


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(max_length=2000)


class PushTestOut(BaseModel):
    sent: int
    removed: int
    failed: int
