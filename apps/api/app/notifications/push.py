"""Web Push — the bell reaches a phone even when the CRM is closed.

Flow: `notify()` stages a Notification → `queue_push_after_commit` remembers
it on the session → only after a successful COMMIT the Celery task
`send_push` is enqueued (a rolled-back notification never buzzes a phone)
→ the worker signs with VAPID and posts to every subscription of the user.

Off while VAPID keys are empty: subscriptions are stored, nothing is sent.
Keys: `python -m app.notifications.push keys` — prints a fresh pair for the
env file deploy.sh uses (`shared/.env`, else `infra/production/.env`).
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.notifications.models import Notification, PushSubscription

log = structlog.get_logger()

# Events worth a buzz on a phone. Everything else stays in the bell.
PUSH_KINDS: frozenset[str] = frozenset({
    "lead_inbound",
    "email_inbound",
    "mention",
    "task_assigned",
    "leads_assigned",
})

# Shown on a locked screen: keep client detail to the title. The email
# subject and comment text stay inside the CRM.
_BODY_HIDDEN_KINDS: frozenset[str] = frozenset({"email_inbound", "mention"})

_PENDING_KEY = "drinkx_pending_push"


def push_enabled() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def build_payload(n: Notification) -> dict[str, Any]:
    """What the service worker shows. Pure — unit-tested."""
    return {
        "title": n.title,
        "body": "" if n.kind in _BODY_HIDDEN_KINDS else (n.body or ""),
        "url": f"/leads/{n.lead_id}" if n.lead_id else "/today",
        "tag": str(n.id),
    }


def _after_commit(sync_session) -> None:
    pending: list[Notification] = sync_session.info.pop(_PENDING_KEY, [])
    for n in pending:
        if n.id is None:
            continue
        try:
            from app.scheduled.jobs import send_push

            send_push.delay(str(n.id))
        except Exception as exc:  # noqa: BLE001 — broker hiccup must not break the request
            log.warning("push.enqueue_failed", notification_id=str(n.id), error=str(exc)[:200])


def _after_rollback(sync_session) -> None:
    sync_session.info.pop(_PENDING_KEY, None)


def queue_push_after_commit(db: AsyncSession, row: Notification) -> None:
    """Remember `row` and enqueue its push once the transaction commits.
    No-op for kinds that stay in the bell and for non-real sessions."""
    if row.kind not in PUSH_KINDS or not isinstance(db, AsyncSession):
        return
    sync = db.sync_session
    pending = sync.info.setdefault(_PENDING_KEY, [])
    pending.append(row)
    if not event.contains(sync, "after_commit", _after_commit):
        event.listen(sync, "after_commit", _after_commit)
        event.listen(sync, "after_rollback", _after_rollback)


def _send_one(sub: PushSubscription, payload: dict[str, Any]) -> str:
    """Returns "ok", "gone" (subscription must be deleted) or "error"."""
    from pywebpush import WebPushException, webpush

    s = get_settings()
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject},
            ttl=24 * 60 * 60,
            timeout=10,
        )
        return "ok"
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            return "gone"
        log.warning("push.send_failed", status=status, error=str(exc)[:200])
        return "error"
    except Exception as exc:  # noqa: BLE001 — network trouble, keep the subscription
        log.warning("push.send_failed", error=str(exc)[:200])
        return "error"


async def send_to_user(
    db: AsyncSession, *, user_id: UUID, payload: dict[str, Any]
) -> dict[str, int]:
    """Post `payload` to every subscription of the user; drop gone ones."""
    subs = (
        await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars().all()
    stats = {"ok": 0, "gone": 0, "error": 0}
    gone: list[UUID] = []
    for sub in subs:
        result = await asyncio.to_thread(_send_one, sub, payload)
        stats[result] += 1
        if result == "gone":
            gone.append(sub.id)
    if gone:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
        await db.commit()
    return stats


async def send_push_for_notification(db: AsyncSession, notification_id: UUID) -> dict[str, int]:
    if not push_enabled():
        return {"ok": 0, "gone": 0, "error": 0, "disabled": 1}
    n = await db.get(Notification, notification_id)
    if n is None or n.read_at is not None:
        return {"ok": 0, "gone": 0, "error": 0}
    return await send_to_user(db, user_id=n.user_id, payload=build_payload(n))


def generate_vapid_keys() -> tuple[str, str]:
    """(public, private) as URL-safe base64 without padding — the form
    browsers (applicationServerKey) and pywebpush expect."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    key = ec.generate_private_key(ec.SECP256R1())
    raw_pub = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    raw_priv = key.private_numbers().private_value.to_bytes(32, "big")

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return b64(raw_pub), b64(raw_priv)


if __name__ == "__main__" and sys.argv[1:] == ["keys"]:
    public, private = generate_vapid_keys()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
