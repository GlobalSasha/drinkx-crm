"""Point the backend's stub-mode dev identity at one seeded UX user.

Background: when SUPABASE_URL / SUPABASE_JWT_SECRET are both unset and
APP_ENV != production, app/auth/jwt.py's `_is_stub_mode()` makes every
request authenticate as a single fixed identity:
    sub   = "00000000-0000-0000-0000-000000000001"
    email = "dev@drinkx.tech"
(see app/auth/jwt.py:_stub_claims, ADR-014). That's the ONLY way to reach
the API/UI without a real Supabase project in this environment — see
UX-ENV/README.md for why a genuine browser login is not reproducible
locally without one.

Since the stub identity is a single fixed sub/email, only ONE seeded user
can "be" it at a time. This script moves the stub sub onto a chosen seeded
user's row (clearing it from whoever had it — supabase_user_id is unique),
so the coordinator can switch which role/workspace the running stand is
"logged in as" without restarting anything — just re-run this script and
reload the browser tab / re-issue the curl call.

Usage (from apps/api/, with the UX env vars set — see UX-ENV/README.md):
    python -m scripts.ux_switch_role ux-owner@drinkx.tech
    python -m scripts.ux_switch_role ux-admin2@drinkx.tech   # workspace 2

Only ever targets a disposable database (same allowlist guard as the seed
script).
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.db_safety import assert_disposable  # noqa: E402

STUB_SUB = "00000000-0000-0000-0000-000000000001"
STUB_EMAIL = "dev@drinkx.tech"


async def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m scripts.ux_switch_role <seeded-user-email>", file=sys.stderr)
        return 2
    target_email = sys.argv[1].strip().lower()

    database_url = os.environ.get("DATABASE_URL", "")
    try:
        assert_disposable(database_url, purpose="ux_switch_role")
    except Exception as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    import asyncpg

    conn = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        target = await conn.fetchrow(
            "SELECT id, email, role, workspace_id FROM users WHERE lower(email) = $1",
            target_email,
        )
        if target is None:
            print(f"✗ no user with email {target_email!r} — seed first with scripts.seed_ux_synthetic", file=sys.stderr)
            return 3

        async with conn.transaction():
            # Clear the stub sub from whoever currently holds it (unique constraint).
            await conn.execute(
                "UPDATE users SET supabase_user_id = NULL WHERE supabase_user_id = $1 AND id != $2",
                STUB_SUB,
                target["id"],
            )
            await conn.execute(
                "UPDATE users SET supabase_user_id = $1 WHERE id = $2",
                STUB_SUB,
                target["id"],
            )

        ws = await conn.fetchrow("SELECT name FROM workspaces WHERE id = $1", target["workspace_id"])
        print(f"OK — stub identity ({STUB_EMAIL}) now resolves to:")
        print(f"  {target['email']}  role={target['role']}  workspace={ws['name'] if ws else target['workspace_id']}")
        print("Reload the browser tab / re-issue your API calls to pick this up.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
