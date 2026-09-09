# Plan 024: Redis-backed rate limit for the external API + startup warning for the empty HTTP signing secret

> **Executor instructions**: Follow step by step. Run every verification
> command. Honor STOP conditions. Update this plan's row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/api/app/external/dependencies.py apps/api/app/config.py apps/api/app/automation_builder/services.py`
> Compare against "Current state"; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

Two hardening gaps around the new external surfaces:

1. **Rate limit is per-process, in memory.** The external API's only DoS
   control is an in-memory token bucket, self-documented "Single-replica only."
   With multiple uvicorn workers/replicas the effective limit is 10 rps × N,
   and every deploy resets the buckets. Redis is already a project dependency
   (Celery broker), so a shared bucket is cheap.
2. **HTTP signing secret defaults to empty, silently.** `http_request`
   webhooks are signed with `automation_http_signing_secret`, which defaults to
   `""`. Unlike `fernet_key` (which logs a one-time startup warning when
   empty), there is no warning here — so if it's unset in prod, every outbound
   webhook is signed with an empty HMAC key and the misconfig is invisible.

## Current state

- `apps/api/app/external/dependencies.py:26,45-54` — in-memory bucket:
  ```python
  _RATE_LIMIT_RPS = 10
  _rate_state: dict[uuid.UUID, tuple[float, float]] = {}  # key_id -> (tokens, last_ts)
  def _check_rate_limit(key_id: uuid.UUID) -> None:
      """In-memory token bucket, 10 rps per key. Single-replica only."""
      now = time.monotonic()
      tokens, last = _rate_state.get(key_id, (float(_RATE_LIMIT_RPS), now))
      # ... raises HTTPException(429) when tokens < 1.0 ...
  ```
- `apps/api/app/config.py:170` — `automation_http_signing_secret: str = ""`.
- `apps/api/app/config.py:107-111` — the `fernet_key` empty-key convention
  (comment: "a startup WARNING is logged once"). Find WHERE that warning is
  actually emitted (grep for `fernet_key` in app startup / `main.py` /
  `observability.py`) and mirror it.
- Redis is configured via `REDIS_URL` (see `CLAUDE.md` external services table)
  and used by Celery; find the existing async Redis client/helper
  (`grep -rn "from redis" apps/api/app` / `redis.asyncio`) to reuse rather than
  opening a new connection per request.

## Commands you will need

| Purpose        | Command                                                       | Expected on success |
|----------------|---------------------------------------------------------------|---------------------|
| Compile check  | `cd apps/api && python -m py_compile app/external/dependencies.py app/config.py` | exit 0 |
| External tests | `cd apps/api && uv run pytest -q tests/test_external_auth.py`  | all pass            |

## Scope

**In scope**:
- `apps/api/app/external/dependencies.py` — Redis-backed bucket (with in-memory
  fallback if Redis is down — fail-open on rate limit is acceptable ONLY for
  availability, but prefer fail-closed-ish: on Redis error, fall back to the
  existing in-memory bucket rather than removing the limit entirely)
- `apps/api/app/config.py` — (no new setting required; reuse `REDIS_URL`)
- Startup warning: the module that emits the `fernet_key` warning (likely
  `main.py` lifespan or `observability.py`) — add the signing-secret warning
- `apps/api/tests/test_external_auth.py` — a test for the limiter

**Out of scope**:
- Changing the 10 rps value or per-key semantics.
- The MCP tool logic itself.
- `_sign_http_request_body` behavior (keep HMAC as-is; only warn on empty key).

## Steps

### Step 1: Redis-backed token bucket

Replace the module-level `_rate_state` dict logic with a Redis-backed bucket
keyed by `key_id`. Use a standard atomic pattern (a small Lua script or
`INCR` + `EXPIRE` fixed-window, or a token-bucket via `redis`); a
fixed-window-per-second counter (`INCR extkey:<key_id>:<epoch_second>` with
`EXPIRE 2`) is the simplest correct approach and enough here. On any Redis
exception, fall back to the current in-memory `_check_rate_limit` so a Redis
outage degrades to the old behavior rather than disabling limiting.

**Verify**: `python -m py_compile app/external/dependencies.py` → exit 0.

### Step 2: Startup warning for empty signing secret

Locate where the `fernet_key`-empty warning is logged at startup and add a
sibling warning when `settings.automation_http_signing_secret == ""` and
`app_env == "production"` (or unconditionally, matching the fernet pattern).
Example message: `"automation_http_signing_secret is empty — outbound webhook
signatures are not authenticated"`.

**Verify**: `python -m py_compile <the startup module>` → exit 0;
`grep -rn "automation_http_signing_secret" apps/api/app | grep -i warn` shows
the new log line.

### Step 3: Test the limiter

In `tests/test_external_auth.py`, add a test that N+1 rapid calls with the same
key produce a 429 (mock/monkeypatch the Redis client so the test is
deterministic and doesn't need a live Redis; or use a fakeredis if already a
dep — check `pyproject.toml` first, do NOT add a new dependency without noting
it).

**Verify**: `cd apps/api && uv run pytest -q tests/test_external_auth.py` → all
pass (or deferred to CI, stated).

## Done criteria

- [ ] `python -m py_compile app/external/dependencies.py` exits 0
- [ ] `grep -n "redis" apps/api/app/external/dependencies.py` shows Redis usage
- [ ] Startup warning for empty `automation_http_signing_secret` exists
- [ ] Limiter test exists and passes (or deferred to CI, stated)
- [ ] Redis-down path falls back to in-memory limiting (not "no limit")
- [ ] No files outside the in-scope list modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- No reusable async Redis client exists in the codebase and wiring one up
  cleanly is non-trivial — STOP and report; do not open a raw connection per
  request.
- Adding a fakeredis/test dep is required — note it explicitly and get sign-off
  rather than silently adding a dependency.

## Maintenance notes

- If per-key custom limits are ever needed, the Redis key already namespaces by
  `key_id` — extend there.
- Reviewer: confirm the Redis-outage fallback still limits (in-memory), and the
  429 response shape is unchanged for existing clients.
- Operational follow-up: confirm `AUTOMATION_HTTP_SIGNING_SECRET` is set in prod
  env (the new warning will flag it if not).
