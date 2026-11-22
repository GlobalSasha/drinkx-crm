"""Web Push (mobile phase 3, 22.11.2026): payload, «only after COMMIT»,
dead subscriptions, push-service allowlist, VAPID key format."""
from __future__ import annotations

import base64
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="Requires Postgres")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_payload_hides_email_subject_and_opens_the_lead():
    from app.notifications.models import Notification
    from app.notifications.push import build_payload

    lead_id = uuid.uuid4()
    email = Notification(id=uuid.uuid4(), kind="email_inbound", title="Письмо: Acme",
                         body="Секретная тема", lead_id=lead_id)
    p = build_payload(email)
    assert p == {"title": "Письмо: Acme", "body": "", "url": f"/leads/{lead_id}", "tag": str(email.id)}

    lead = Notification(id=uuid.uuid4(), kind="lead_inbound", title="Новая заявка с сайта",
                        body='"Сайт" — Acme', lead_id=None)
    assert build_payload(lead)["body"] == '"Сайт" — Acme'
    assert build_payload(lead)["url"] == "/today"


@pytest.mark.parametrize("endpoint", [
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://web.push.apple.com/QGh1",
    "https://updates.push.services.mozilla.com/wpush/v2/x",
])
def test_subscription_accepts_real_push_services(endpoint):
    from app.notifications.schemas import PushSubscriptionIn

    PushSubscriptionIn(endpoint=endpoint, keys={"p256dh": "x" * 20, "auth": "y" * 16})


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/abc",
    "https://localhost/push",
    "https://10.0.0.5/push",
    "https://fcm.googleapis.com.evil.example/x",
    "https://evilpush.apple.com.example/x",
])
def test_subscription_rejects_other_addresses(endpoint):
    from app.notifications.schemas import PushSubscriptionIn

    with pytest.raises(ValidationError):
        PushSubscriptionIn(endpoint=endpoint, keys={"p256dh": "x" * 20, "auth": "y" * 16})


def test_generated_vapid_keys_are_usable_by_pywebpush():
    from py_vapid import Vapid

    from app.notifications.push import generate_vapid_keys

    public, private = generate_vapid_keys()
    raw_pub = _b64d(public)
    assert len(raw_pub) == 65 and raw_pub[0] == 0x04
    assert len(_b64d(private)) == 32
    headers = Vapid.from_string(private).sign(
        {"sub": "mailto:admin@drinkx.tech", "aud": "https://fcm.googleapis.com"}
    )
    assert headers["Authorization"].startswith("vapid t=")


@skip_no_pg
async def test_push_is_enqueued_only_after_commit(db, workspace, user):
    from app.notifications.services import notify

    fake = MagicMock()
    with patch("app.scheduled.jobs.send_push", fake):
        row = await notify(db, workspace_id=workspace.id, user_id=user.id,
                           kind="lead_inbound", title="Новая заявка с сайта")
        fake.delay.assert_not_called()
        await db.commit()
        fake.delay.assert_called_once_with(str(row.id))

        # Kinds that stay in the bell never buzz a phone.
        await notify(db, workspace_id=workspace.id, user_id=user.id,
                     kind="enrichment_done", title="AI Brief")
        await db.commit()
        assert fake.delay.call_count == 1

        # Rolled back — no push.
        await notify(db, workspace_id=workspace.id, user_id=user.id,
                     kind="mention", title="Вас упомянули")
        await db.rollback()
        await db.commit()
        assert fake.delay.call_count == 1


@skip_no_pg
async def test_send_drops_gone_subscriptions_and_skips_read(db, workspace, user):
    from sqlalchemy import select

    from app.notifications import push
    from app.notifications.models import Notification, PushSubscription

    alive = PushSubscription(workspace_id=workspace.id, user_id=user.id,
                             endpoint="https://fcm.googleapis.com/fcm/send/alive",
                             p256dh="k" * 20, auth="a" * 16)
    dead = PushSubscription(workspace_id=workspace.id, user_id=user.id,
                            endpoint="https://web.push.apple.com/dead",
                            p256dh="k" * 20, auth="a" * 16)
    n = Notification(workspace_id=workspace.id, user_id=user.id, kind="lead_inbound",
                     title="Новая заявка с сайта", body="")
    db.add_all([alive, dead, n])
    await db.flush()

    sent: list[str] = []

    def fake_send(sub, payload):
        sent.append(sub.endpoint)
        return "gone" if sub.endpoint.endswith("dead") else "ok"

    with patch.object(push, "push_enabled", return_value=True), \
         patch.object(push, "_send_one", side_effect=fake_send):
        stats = await push.send_push_for_notification(db, n.id)
        assert stats == {"ok": 1, "gone": 1, "error": 0}
        left = (await db.execute(
            select(PushSubscription.endpoint).where(PushSubscription.user_id == user.id)
        )).scalars().all()
        assert left == ["https://fcm.googleapis.com/fcm/send/alive"]

        # Already read in the bell — no buzz.
        from datetime import datetime, timezone
        n.read_at = datetime.now(timezone.utc)
        await db.flush()
        sent.clear()
        assert (await push.send_push_for_notification(db, n.id))["ok"] == 0
        assert sent == []


@skip_no_pg
async def test_send_is_noop_without_vapid_keys(db, workspace, user):
    from app.notifications import push
    from app.notifications.models import Notification

    n = Notification(workspace_id=workspace.id, user_id=user.id, kind="lead_inbound",
                     title="t", body="")
    db.add(n)
    await db.flush()
    with patch.object(push, "push_enabled", return_value=False), \
         patch.object(push, "_send_one") as send_one:
        stats = await push.send_push_for_notification(db, n.id)
    assert stats.get("disabled") == 1
    send_one.assert_not_called()
