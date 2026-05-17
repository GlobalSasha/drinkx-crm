"""Create a test manager account for UI auditing (v0 browser agent, etc.).

Creates a Supabase auth user with email+password (no Google OAuth needed),
inserts the matching `users` row into the CRM with role=manager, and assigns
~10-15 currently-unassigned leads to the test user so the dashboard has
real data to navigate.

Idempotent: re-running the script updates the existing user's password and
tops up its lead assignment instead of creating duplicates.

Run inside the api container on prod:

    docker exec -i drinkx-api-1 python scripts/create_test_user.py

Requires SUPABASE_URL, SUPABASE_SECRET_KEY, DATABASE_URL in the env (already
set on the production container).
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

import httpx

TEST_EMAIL = "test@drinkx.tech"
TEST_PASSWORD = "DrinkX_Test_2026!"
TEST_NAME = "Тест Менеджер"
LEAD_TARGET = 12  # 10-15 range


async def supabase_upsert_user(
    *, base_url: str, service_key: str, email: str, password: str, name: str
) -> str:
    """Create or update the Supabase auth user. Returns the auth user id."""
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/json",
    }
    create_payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"name": name, "test_account": True},
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            f"{base_url}/auth/v1/admin/users", headers=headers, json=create_payload
        )

        if res.status_code in (200, 201):
            return res.json()["id"]

        body = res.text[:500]

        # 422 = user already registered. Look them up and reset the password.
        if res.status_code == 422 and "already" in body.lower():
            lookup = await client.get(
                f"{base_url}/auth/v1/admin/users",
                headers=headers,
                params={"email": email},
            )
            lookup.raise_for_status()
            users = lookup.json().get("users") or []
            if not users:
                raise RuntimeError(
                    f"Supabase says user exists but lookup returned no rows: {body}"
                )
            user_id = users[0]["id"]

            update = await client.put(
                f"{base_url}/auth/v1/admin/users/{user_id}",
                headers=headers,
                json={"password": password, "email_confirm": True},
            )
            update.raise_for_status()
            return user_id

        # 501 / "Email provider disabled" — surface clearly so the operator
        # can flip it on in the Supabase dashboard before retrying.
        if (
            res.status_code in (400, 422, 501)
            and "email" in body.lower()
            and ("disabled" in body.lower() or "not enabled" in body.lower())
        ):
            raise RuntimeError(
                "Email/password provider is disabled in Supabase. Enable it in "
                "Dashboard → Authentication → Providers → Email, then re-run.\n"
                f"Supabase response: {body}"
            )

        raise RuntimeError(
            f"Supabase admin createUser failed: {res.status_code} {body}"
        )


async def main() -> int:
    import asyncpg

    supabase_url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SECRET_KEY") or ""
    db_url = (os.environ.get("DATABASE_URL") or "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )

    if not supabase_url or not service_key:
        print("✗ SUPABASE_URL / SUPABASE_SECRET_KEY not set", file=sys.stderr)
        return 2
    if not db_url:
        print("✗ DATABASE_URL not set", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(db_url)
    try:
        ws = await conn.fetchrow(
            "SELECT id, name FROM workspaces ORDER BY created_at ASC LIMIT 1"
        )
        if ws is None:
            print("✗ No workspace found in DB — sign in once first to bootstrap.", file=sys.stderr)
            return 3
        workspace_id = ws["id"]

        try:
            supabase_user_id = await supabase_upsert_user(
                base_url=supabase_url,
                service_key=service_key,
                email=TEST_EMAIL,
                password=TEST_PASSWORD,
                name=TEST_NAME,
            )
        except RuntimeError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 4

        now = datetime.now(timezone.utc)

        # Upsert the CRM user row by email. Email is unique.
        row = await conn.fetchrow(
            """
            INSERT INTO users (
                id, workspace_id, email, name, role,
                supabase_user_id, onboarding_completed, last_login_at,
                created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), $1, $2, $3, 'manager',
                $4, TRUE, $5,
                $5, $5
            )
            ON CONFLICT (email) DO UPDATE
            SET supabase_user_id = EXCLUDED.supabase_user_id,
                name = EXCLUDED.name,
                role = 'manager',
                onboarding_completed = TRUE,
                last_login_at = EXCLUDED.last_login_at,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            workspace_id,
            TEST_EMAIL,
            TEST_NAME,
            supabase_user_id,
            now,
        )
        user_id = row["id"]

        # Count what's already assigned to this user, then top up to LEAD_TARGET.
        already = await conn.fetchval(
            "SELECT COUNT(*) FROM leads WHERE assigned_to = $1 "
            "AND assignment_status = 'assigned'",
            user_id,
        )

        to_assign = max(0, LEAD_TARGET - int(already or 0))
        newly_assigned = 0
        if to_assign > 0:
            rows = await conn.fetch(
                """
                WITH picked AS (
                    SELECT id FROM leads
                    WHERE workspace_id = $1
                      AND assignment_status = 'pool'
                    ORDER BY created_at DESC
                    LIMIT $2
                )
                UPDATE leads
                SET assignment_status = 'assigned',
                    assigned_to = $3,
                    assigned_at = $4
                WHERE id IN (SELECT id FROM picked)
                RETURNING id
                """,
                workspace_id,
                to_assign,
                user_id,
                now,
            )
            newly_assigned = len(rows)

        total_assigned = await conn.fetchval(
            "SELECT COUNT(*) FROM leads WHERE assigned_to = $1 "
            "AND assignment_status = 'assigned'",
            user_id,
        )

        print("✅ Test user created")
        print(f"Email: {TEST_EMAIL}")
        print(f"Password: {TEST_PASSWORD}")
        print("URL: https://crm.drinkx.tech")
        print(f"Leads assigned: {total_assigned} (newly: {newly_assigned})")
        print(f"User ID: {user_id}")
        print(f"Supabase auth ID: {supabase_user_id}")
        print(f"Workspace: {ws['name']} ({workspace_id})")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
