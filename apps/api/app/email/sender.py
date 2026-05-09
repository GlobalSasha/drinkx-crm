"""SMTP sender for the Automation Builder's `send_template` action —
Sprint 2.6 G1.

Tri-state contract (distinct from `app.notifications.email_sender`):
  - Returns `True` when SMTP_HOST is set and the send succeeded.
  - Returns `False` when SMTP_HOST is empty (stub mode — message is
    logged via structlog, no network I/O).
  - Raises `EmailSendError` when SMTP_HOST is set but the send fails.

The two return states + one exception let the caller distinguish
«delivered» / «would have sent» / «tried and failed» — three different
chips on the Activity Feed, three different audit-trail entries on
`automation_runs`.

Why a separate module from `app.notifications.email_sender`:
  - The notifications sender treats stub mode as success (returns
    True) so the daily-digest cron tick is testable end-to-end on
    SMTP-less staging deploys. Reusing that contract here would
    collapse the «sent» vs «stub» distinction the Activity Feed
    needs to surface.
  - Plain-text body (the Automation Builder's render output is
    plain text per `app.automation_builder.render`), no HTML
    multipart shenanigans. Different concern, different module.
"""
from __future__ import annotations

from email.message import EmailMessage

import structlog

from app.config import Settings, get_settings

log = structlog.get_logger()


class EmailSendError(Exception):
    """Raised when SMTP_HOST is set but `aiosmtplib.send` fails.
    Caller (the action handler) catches this and writes
    `automation_runs.status='failed'` with the error truncated to 500
    chars."""


async def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    settings: Settings | None = None,
) -> bool:
    """Send a plain-text email. Returns True on real send, False in
    stub mode, raises `EmailSendError` on SMTP failure.

    `settings` is optional — defaults to the global `get_settings()`.
    Tests inject a custom Settings to flip stub-vs-real without
    monkeypatching the cache.
    """
    s = settings or get_settings()

    if not s.smtp_host:
        # Stub mode — no network I/O. Logged so ops can grep for what
        # would have gone out during a staging window.
        log.info(
            "[EMAIL STUB outbound]",
            to=to,
            subject=subject,
            body_preview=body[:200],
        )
        return False

    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        # Lazy import keeps the dep optional in stub mode and in test
        # paths that never actually hit the SMTP branch — same shape
        # as `app.notifications.email_sender`.
        import aiosmtplib

        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_user or None,
            password=s.smtp_password or None,
            start_tls=True,
            timeout=20,
        )
    except Exception as exc:
        # Catch-all → re-raise as our typed error so the action
        # handler can map it cleanly to `automation_runs.status`.
        # Truncation happens at the run-row layer, not here.
        log.warning(
            "email.send_failed",
            to=to,
            subject=subject,
            error=str(exc)[:300],
        )
        raise EmailSendError(str(exc)[:500]) from exc

    log.info("email.sent", to=to, subject=subject)
    return True
