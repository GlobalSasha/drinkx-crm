"""Channel adapters for messenger / phone integrations — Sprint 3.4.

Each adapter implements `ChannelAdapter` (see `base.py`) and converts
provider-specific webhook JSON into the unified `WebhookPayload`
schema. Sending is symmetric: `OutboundMessage` → provider API.

Adapters live alongside `app.inbox.gmail_client` etc. — Gmail itself
stays out of this protocol because its lifecycle (read-only sync with
triage queue) is fundamentally different from real-time chat.
"""
