"""Gmail sync survives a rollback in the middle of a tick.

A rollback expires every object in the session. Reading a column of an expired
object then needs a database round trip that an async session can't do
implicitly, so it raises `MissingGreenlet`. In production one mailbox failing
at saving its credentials took down the whole tick, and the Celery task still
reported success. Needs PostgreSQL: mocks don't reproduce expired state.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

import app.main  # noqa: F401  — configures the SQLAlchemy mappers
from tests.conftest import POSTGRES_AVAILABLE

pytestmark = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


class FakeGmailClient:
    """Stands in for Gmail: one new message per history entry, no network."""

    instances = 0
    fail_first_instance = False

    def __init__(self, credentials_json: str):
        cls = type(self)
        cls.instances += 1
        self.is_failing = cls.fail_first_instance and cls.instances == 1

    async def get_history(self, *, start_history_id: str):
        return [
            {"id": "200", "messagesAdded": [{"message": {"id": "m1"}}]},
            {"id": "201", "messagesAdded": [{"message": {"id": "m2"}}]},
        ]

    async def list_messages(self, *, query: str | None = None, max_results: int = 500):
        return [{"id": "m1"}, {"id": "m2"}]

    async def get_message(self, msg_id: str):
        return {"id": msg_id}

    async def get_profile(self):
        return {"historyId": "300"}

    def refreshed_credentials_json(self) -> str:
        if self.is_failing:
            from app.inbox.crypto import CredentialsCryptoError

            raise CredentialsCryptoError("FERNET_KEY is not configured in production")
        return "{}"


@pytest_asyncio.fixture
async def mailboxes(monkeypatch):
    """Two users with an active Gmail channel, committed like in production.

    The sync code commits and rolls back on its own, so the rows can't live in
    the rolled-back-per-test `db` session. Deleting the workspace cleans up.
    """
    from app.auth.models import User, Workspace
    from app.inbox.models import ChannelConnection
    from tests.conftest import _test_session_factory

    monkeypatch.setattr(FakeGmailClient, "instances", 0)
    monkeypatch.setattr(FakeGmailClient, "fail_first_instance", False)
    monkeypatch.setattr("app.inbox.sync.GmailClient", FakeGmailClient)

    async with _test_session_factory() as session:
        ws = Workspace(name="Gmail WS", plan="pro", sprint_capacity_per_week=20)
        session.add(ws)
        await session.flush()
        conn_ids = []
        user_ids = []
        for _ in range(2):
            user = User(
                workspace_id=ws.id,
                email=f"mbox-{uuid.uuid4().hex[:8]}@test.com",
                name="Менеджер",
                role="manager",
            )
            session.add(user)
            await session.flush()
            conn = ChannelConnection(
                workspace_id=ws.id,
                user_id=user.id,
                channel_type="gmail",
                credentials_json="{}",
                status="active",
                extra_json={"last_history_id": "100"},
            )
            session.add(conn)
            await session.flush()
            conn_ids.append(conn.id)
            user_ids.append(user.id)
        ws_id = ws.id
        await session.commit()

    yield {"workspace_id": ws_id, "conn_ids": conn_ids, "user_ids": user_ids}

    async with _test_session_factory() as session:
        await session.delete(await session.get(Workspace, ws_id))
        await session.commit()


async def _cursors(conn_ids) -> list[str | None]:
    from app.inbox.models import ChannelConnection
    from tests.conftest import _test_session_factory

    async with _test_session_factory() as session:
        conns = [await session.get(ChannelConnection, cid) for cid in conn_ids]
        return [(c.extra_json or {}).get("last_history_id") for c in conns]


@pytest.mark.asyncio
async def test_one_failing_mailbox_does_not_kill_the_tick(mailboxes, monkeypatch):
    """The production failure: the first mailbox can't save its credentials,
    the rollback expires the second one, and reading it must still work."""
    from app.inbox.sync import incremental_sync_for_all
    from tests.conftest import _test_session_factory

    monkeypatch.setattr(FakeGmailClient, "fail_first_instance", True)
    seen: list[str] = []

    async def fake_process(session, *, raw_message, user_id, workspace_id):
        seen.append(raw_message["id"])
        return True

    monkeypatch.setattr("app.inbox.sync.process_message", fake_process)

    async with _test_session_factory() as session:
        processed = await incremental_sync_for_all(session)

    # Both mailboxes had their messages read; only the healthy one finished.
    assert seen == ["m1", "m2", "m1", "m2"]
    assert processed == 2
    assert sorted(await _cursors(mailboxes["conn_ids"]), key=str) == ["100", "201"]


@pytest.mark.asyncio
async def test_bad_message_does_not_lose_the_rest_of_the_mailbox(mailboxes, monkeypatch):
    """`process_message` rolls back on a bad message. The next message must
    still go through, and the cursor must still advance."""
    from app.inbox.sync import incremental_sync_for_all
    from tests.conftest import _test_session_factory

    calls: list[tuple[str, uuid.UUID | None, uuid.UUID]] = []

    async def fake_process(session, *, raw_message, user_id, workspace_id):
        calls.append((raw_message["id"], user_id, workspace_id))
        if raw_message["id"] == "m1":
            await session.rollback()
            return False
        return True

    monkeypatch.setattr("app.inbox.sync.process_message", fake_process)

    async with _test_session_factory() as session:
        processed = await incremental_sync_for_all(session)

    assert processed == 4
    assert [c[0] for c in calls] == ["m1", "m2", "m1", "m2"]
    assert {c[2] for c in calls} == {mailboxes["workspace_id"]}
    assert {c[1] for c in calls} == set(mailboxes["user_ids"])
    assert await _cursors(mailboxes["conn_ids"]) == ["201", "201"]


@pytest.mark.asyncio
async def test_history_sync_survives_a_bad_message(mailboxes, monkeypatch):
    """Same rollback, in the one-time backfill that runs after connecting."""
    from app.inbox.sync import history_sync_for_user
    from tests.conftest import _test_session_factory

    calls: list[str] = []

    async def fake_process(session, *, raw_message, user_id, workspace_id):
        calls.append(raw_message["id"])
        assert workspace_id == mailboxes["workspace_id"]
        if raw_message["id"] == "m1":
            await session.rollback()
            return False
        return True

    monkeypatch.setattr("app.inbox.sync.process_message", fake_process)

    async with _test_session_factory() as session:
        processed = await history_sync_for_user(
            session, user_id=mailboxes["user_ids"][0]
        )

    assert calls == ["m1", "m2"]
    assert processed == 2
    assert (await _cursors(mailboxes["conn_ids"]))[0] == "300"
