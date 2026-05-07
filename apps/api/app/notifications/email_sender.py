"""SMTP email sender — Sprint 1.5.

Stub mode: when SMTP_HOST is empty, the rendered email is logged to
stdout via structlog (prefix `[EMAIL STUB]`) and `send_email()` returns
True. This mirrors the ADR-014 stub-mode pattern used by the LLM
fallback chain — staging deploys can run the digest tick end-to-end
without a real SMTP relay.

Production mode: aiosmtplib STARTTLS to SMTP_HOST:SMTP_PORT, login with
SMTP_USER / SMTP_PASSWORD, send a multipart message with the rendered
HTML body. Never raises — failures are logged and `False` is returned.
"""
from __future__ import annotations

from email.message import EmailMessage

import structlog

from app.config import get_settings

log = structlog.get_logger()


async def send_email(*, to: str, subject: str, html: str) -> bool:
    """Send one HTML email. Returns True on success/stub, False on failure."""
    s = get_settings()

    if not s.smtp_host:
        # Stub mode — log preview, pretend the send succeeded.
        log.info(
            "[EMAIL STUB]",
            to=to,
            subject=subject,
            html_preview=html[:200],
        )
        return True

    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("Откройте письмо в HTML-режиме, чтобы увидеть оформление.")
    msg.add_alternative(html, subtype="html")

    try:
        # Lazy import keeps the dep optional in stub mode (e.g. local dev
        # / unit tests) — no import error if aiosmtplib isn't installed.
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
        log.info("email.sent", to=to, subject=subject)
        return True
    except Exception as exc:
        log.warning(
            "email.send_failed",
            to=to,
            subject=subject,
            error=str(exc)[:300],
        )
        return False
