"""ChannelAdapter Protocol — Sprint 3.4 G1.

A channel adapter is the thin translation layer between a provider's
webhook / send API and the unified inbox. It does not know about
SQLAlchemy, leads, or workspace authorization — those concerns belong
to `app.inbox.message_services`.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.inbox.schemas import OutboundMessage, WebhookPayload


@runtime_checkable
class ChannelAdapter(Protocol):
    """One adapter per channel — telegram, max, phone."""

    channel: str

    async def parse_webhook(self, raw: dict) -> WebhookPayload:
        """Convert provider webhook JSON to the unified payload."""
        ...

    async def send(self, msg: OutboundMessage) -> str:
        """Send an outbound message. Returns provider message id."""
        ...
