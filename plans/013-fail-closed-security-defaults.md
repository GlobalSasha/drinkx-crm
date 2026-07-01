# Plan 013: Fail-closed security defaults — auth stub-mode and the Mango phone webhook

> **Executor instructions**: Follow step by step; run every verification command.
> Honor STOP conditions. Update plan 013's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/auth/jwt.py apps/api/app/inbox/webhooks.py`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW (both changes only *reject* in a misconfigured state that should never be production)
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `9e93b16`, 2026-07-01
- **Implements**: round-2 backlog **B10** (Mango webhook fail-closed)

## Why this matters

Two paths default to *open* instead of *closed*:

1. **Auth stub mode.** `verify_token` short-circuits to a fixed dev identity whenever
   *both* `SUPABASE_JWT_SECRET` and `SUPABASE_URL` are unset — with no token check.
   If production ever boots with those env vars missing, every request is silently
   authenticated as the stub user (and on an empty DB, "first user becomes admin"
   makes that stub an admin). A single missing env var flips auth off with no loud
   failure.
2. **Mango phone webhook.** When `mango_api_salt` is unset, the `/api/webhooks/phone`
   endpoint accepts **unsigned** payloads with only a `log.warning` — i.e. an
   unauthenticated write path that creates call Activities. The sibling Telegram
   handler already fails closed (503 when its secret is unset). Mango should match.

Both are cheap to make fail-closed while preserving the local-dev convenience.

## Current state

**Auth** — `apps/api/app/auth/jwt.py`:
```python
def _is_stub_mode() -> bool:                                   # line 39
    s = get_settings()
    return not s.supabase_jwt_secret and not s.supabase_url

async def verify_token(token) -> TokenClaims:                  # line 102
    if _is_stub_mode():
        return _stub_claims()                                  # line 110 — no token check
    ...
```
- Config has `app_env: str = "development"` (values `development|staging|production`)
  at `apps/api/app/config.py:14` — use it to allow stub mode only outside production.

**Mango** — `apps/api/app/inbox/webhooks.py`:
```python
    if s.mango_api_salt:                                       # line 161
        expected = compute_sign(s.mango_api_key, signed_blob, s.mango_api_salt)
        if not presented_sign or not secrets.compare_digest(presented_sign, expected):
            raise HTTPException(401, "invalid_sign")
    else:
        log.warning("inbox.webhook.phone.unsigned_accepted")   # line 175 — accepts unsigned
```
- Telegram exemplar (fail-closed) in the same file:
  ```python
  if not s.telegram_webhook_secret:                            # line 86
      raise HTTPException(503, "telegram_webhook_not_configured")
  ```

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/auth/jwt.py app/inbox/webhooks.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/auth/jwt.py app/inbox/webhooks.py` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q tests/test_failclosed_defaults.py` | all pass |

## Scope

**In scope:**
- `apps/api/app/auth/jwt.py` (gate stub mode to non-production)
- `apps/api/app/inbox/webhooks.py` (fail closed when Mango salt unset)
- `apps/api/tests/test_failclosed_defaults.py` (create)

**Out of scope:**
- The single-tenant `_resolve_workspace_id` shim (B10's second half — per-connection
  routing is deferred until a 2nd tenant; leave the shim, it's documented).
- Any change to the *happy* auth path (valid Supabase token) or the Telegram handler.
- `compute_sign` / the signing formula.

## Git workflow

- Branch: `advisor/013-fail-closed`
- One commit: `fix(security): fail closed on auth stub-in-prod and unsigned Mango webhook (plan 013, B10)`.

## Steps

### Step 1: Stub mode is dev-only, never production

Change `_is_stub_mode` (or `verify_token`) so stub identity is returned **only** when
`app_env != "production"`. In production with missing Supabase env, raise a loud 500
at request time instead of silently authenticating:
```python
def _is_stub_mode() -> bool:
    s = get_settings()
    if s.supabase_jwt_secret or s.supabase_url:
        return False
    if s.app_env == "production":
        raise HTTPException(
            status_code=500,
            detail="auth misconfigured: SUPABASE_URL/JWT secret unset in production",
        )
    return True
```
(Or keep `_is_stub_mode` boolean and put the production guard at the top of
`verify_token` — either is fine; the invariant is: **no stub identity in production**.)

**Verify**: `grep -n "app_env" app/auth/jwt.py` → present in the stub gate.
`python -m py_compile app/auth/jwt.py` → 0.

### Step 2: Mango webhook fails closed when salt unset

Mirror the Telegram handler: when `s.mango_api_salt` is empty, reject rather than
accept. To preserve local dev (no salt), gate the leniency to non-production:
```python
    if not s.mango_api_salt:
        if s.app_env == "production":
            log.error("inbox.webhook.phone.no_salt_configured")
            raise HTTPException(503, "phone_webhook_not_configured")
        log.warning("inbox.webhook.phone.unsigned_accepted_dev_only")
    else:
        expected = compute_sign(...)
        if not presented_sign or not secrets.compare_digest(presented_sign, expected):
            raise HTTPException(401, "invalid_sign")
```

**Verify**: `grep -n "phone_webhook_not_configured\|app_env" app/inbox/webhooks.py`
→ present. `python -m py_compile app/inbox/webhooks.py` → 0.

### Step 3: Tests

Create `tests/test_failclosed_defaults.py` (mock `get_settings`). Cases:
`app_env='development'` + no Supabase env → stub identity returned; `app_env='production'`
+ no Supabase env → raises (no stub identity); Mango: production + no salt → 503;
development + no salt → accepted (unsigned, dev only); any env + salt set + bad sign
→ 401.

**Verify**: `cd apps/api && uv run pytest -q tests/test_failclosed_defaults.py` → all pass.

## Test plan

- New `tests/test_failclosed_defaults.py`, ~5 cases (Step 3), mock-only.
- Pattern: an existing test that monkeypatches `get_settings` (`grep -rln "get_settings" tests`).
- Verification: pytest command passes.

## Done criteria

- [ ] `python -m py_compile app/auth/jwt.py app/inbox/webhooks.py` → 0
- [ ] `uv run ruff check app/auth/jwt.py app/inbox/webhooks.py` → 0
- [ ] `uv run pytest -q tests/test_failclosed_defaults.py` → all pass
- [ ] No stub identity is reachable when `app_env == "production"` (asserted)
- [ ] Mango webhook returns 503 (not 200) in production with no salt (asserted)
- [ ] No files outside scope modified (`git status`)
- [ ] `plans/README.md` round-3 row for 013 updated; mark B10 as covered

## STOP conditions

- Excerpts don't match live code (drift) — report.
- Production actually relies on stub mode for some job/health path (grep for
  `is_stub`) — if any non-dev caller depends on stub identity, STOP and report before
  changing the gate.
- `app_env` is not reliably set to `"production"` on the prod server — if unclear how
  prod sets it, STOP; a wrong assumption here could 500 all of prod. (Confirm via
  `infra/production/` env before shipping.)

## Maintenance notes

- The remaining half of B10 (per-`ChannelConnection` workspace routing instead of the
  "first workspace" shim) is intentionally deferred to when a second tenant exists.
- Reviewer: verify the dev convenience still works (local `pnpm`/`uv` run with no
  Supabase env should still boot and authenticate as the stub user).
