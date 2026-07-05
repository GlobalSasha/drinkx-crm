"""Issue or revoke a machine API key for external OS access.

Usage:
    python -m scripts.issue_service_key issue --workspace <uuid> --name "OS DrinkX"
    python -m scripts.issue_service_key revoke --key-id <uuid>
    python -m scripts.issue_service_key list --workspace <uuid>

`issue` prints the full token ONCE — store it in the OS `.env`. The DB
keeps only the sha256 hash.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import get_session_factory
from app.external import keys
from app.external.models import ServiceApiKey


async def _issue(workspace_id: uuid.UUID, name: str) -> None:
    token, key_hash = keys.generate_key()
    async with get_session_factory()() as s:
        row = ServiceApiKey(
            workspace_id=workspace_id, name=name, key_hash=key_hash, scopes=["read:core"]
        )
        s.add(row)
        await s.commit()
        print(f"key_id={row.id}")
    print("TOKEN (store now, shown once):")
    print(token)


async def _revoke(key_id: uuid.UUID) -> None:
    async with get_session_factory()() as s:
        row = (
            await s.execute(select(ServiceApiKey).where(ServiceApiKey.id == key_id))
        ).scalar_one_or_none()
        if row is None:
            print("not found")
            return
        row.revoked_at = datetime.now(timezone.utc)
        await s.commit()
        print(f"revoked {key_id}")


async def _list(workspace_id: uuid.UUID) -> None:
    async with get_session_factory()() as s:
        rows = (
            await s.execute(
                select(ServiceApiKey).where(ServiceApiKey.workspace_id == workspace_id)
            )
        ).scalars().all()
        for r in rows:
            status = "revoked" if r.revoked_at else "active"
            print(f"{r.id}  {status:8}  {r.name}  last_used={r.last_used_at}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("issue"); pi.add_argument("--workspace", required=True); pi.add_argument("--name", required=True)
    pr = sub.add_parser("revoke"); pr.add_argument("--key-id", required=True)
    pl = sub.add_parser("list"); pl.add_argument("--workspace", required=True)
    args = p.parse_args()
    if args.cmd == "issue":
        asyncio.run(_issue(uuid.UUID(args.workspace), args.name))
    elif args.cmd == "revoke":
        asyncio.run(_revoke(uuid.UUID(args.key_id)))
    elif args.cmd == "list":
        asyncio.run(_list(uuid.UUID(args.workspace)))


if __name__ == "__main__":
    main()
