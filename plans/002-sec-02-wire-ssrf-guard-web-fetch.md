# Plan 002: Wire the SSRF guard into `WebFetch` (enrichment website fetch)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat d68a3e9..HEAD -- apps/api/app/enrichment/sources/web_fetch.py apps/api/app/common/ssrf.py apps/api/app/enrichment/orchestrator.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `d68a3e9`, 2026-06-11

## Why this matters

The enrichment pipeline fetches a lead's `website` URL server-side to scrape page
text for the LLM. A manager controls `lead.website`, so they can point it at an
internal address — e.g. `http://169.254.169.254/latest/meta-data/` (cloud
instance metadata / credentials), `http://localhost:8000/...`, or a private
`10.x`/`192.168.x` service — and the server will fetch it and return the body into
the enrichment context. That is a classic **authenticated SSRF**.

The codebase already contains the correct defense — `app/common/ssrf.py`
(`is_safe_fetch_url`, `is_public_host`) — but it is **dead code**: a repo-wide grep
shows it is defined and never called. `WebFetch.fetch` makes the request with **no
host validation** and **`follow_redirects=True`**, so even a "safe" public URL can
302-redirect into an internal address (the guard's own docstring warns about this
DNS/redirect rebinding). This plan wires the guard in and removes auto-redirect in
favor of manual, re-validated redirect following.

## Current state

Files in scope:
- `apps/api/app/enrichment/sources/web_fetch.py` — `WebFetch.fetch`; makes the
  HTTP request with no SSRF check and `follow_redirects=True`.
- `apps/api/app/common/ssrf.py` — the guard. `is_safe_fetch_url(url)` returns
  `True` only if `url` is http(s) and its hostname resolves to a public IP;
  `is_public_host(host)` does the DNS resolution + private/loopback/link-local/
  reserved/multicast/unspecified rejection.
- `apps/api/app/enrichment/sources/base.py` — defines `SourceResult` (the return
  type; has `source`, `query`, `items`, `error`, `elapsed_ms`, `cached` fields —
  confirm exact fields before editing).
- `apps/api/app/enrichment/orchestrator.py:680` — the call site
  `web_source.fetch(lead.website, use_cache=True)` (read-only context; no change
  needed once the guard lives inside `WebFetch`).

`is_safe_fetch_url` (today, `apps/api/app/common/ssrf.py:45`):

```python
def is_safe_fetch_url(url: str) -> bool:
    """True if `url` is an http(s) URL whose host resolves to a public IP."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.hostname:
        return False
    return is_public_host(parsed.hostname)
```

The vulnerable request, today (`apps/api/app/enrichment/sources/web_fetch.py`,
inside `WebFetch.fetch`):

```python
        # Reject obviously bad inputs early
        try:
            parsed = urlparse(url)
        except ValueError as e:
            return SourceResult(source=self.name, query=url, error=f"bad url: {e}")
        if parsed.scheme not in ("http", "https"):
            return SourceResult(source=self.name, query=url, error="non-http scheme")
        if not parsed.netloc:
            return SourceResult(source=self.name, query=url, error="no host")

        if use_cache:
            cached = await cache_get(self.name, url)
            ...

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, max_redirects=3) as client:
                resp = await client.get(url, headers=headers)
        except httpx.TimeoutException as e:
            return SourceResult(source=self.name, query=url, error=f"timeout: {e}")
        except httpx.HTTPError as e:
            return SourceResult(source=self.name, query=url, error=f"http: {e}")
```

Repo conventions to follow:
- `web_fetch.py` already returns failures as `SourceResult(..., error="...")`
  rather than raising. Match that: a blocked URL returns an error `SourceResult`,
  it does not raise.
- Structured logging via `structlog` (`log = structlog.get_logger()` is already in
  the file). Log a blocked fetch at warning level.
- Tests for enrichment sources use `respx` (declared in dev deps) to mock httpx.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run the new test | `cd apps/api && uv run pytest tests/test_web_fetch_ssrf.py -q` | all pass |
| Related source tests | `cd apps/api && uv run pytest tests/ -q -k "enrichment or web_fetch or source"` | all pass (no regression) |
| Lint | `cd apps/api && uv run ruff check app/enrichment/sources/web_fetch.py app/common/ssrf.py tests/test_web_fetch_ssrf.py` | exit 0 |
| Typecheck | `cd apps/api && uv run mypy app/enrichment/sources/web_fetch.py app/common/ssrf.py` | exit 0 |

These tests are pure (respx-mocked HTTP, monkeypatched DNS) and do NOT require
Postgres — they run regardless of DB availability.

## Scope

**In scope** (the only files you may modify):
- `apps/api/app/enrichment/sources/web_fetch.py` — add the SSRF check + manual
  redirect re-validation.
- `apps/api/tests/test_web_fetch_ssrf.py` — create.

**Out of scope** (do NOT touch):
- `apps/api/app/common/ssrf.py` — the guard is correct; reuse it, don't change it.
- `apps/api/app/enrichment/orchestrator.py` — once the guard is inside `WebFetch`,
  the call site is automatically protected; no edit needed.
- `apps/api/app/enrichment/sources/rss_feed.py` — RSS feed URLs are a *separate*
  user-controlled fetch surface with the same exposure, but they are not in this
  plan's scope. Note them in your report as a follow-up (see Maintenance notes).
- Any change to `SourceResult`'s shape.

## Git workflow

- Branch: `advisor/002-sec-wire-ssrf-guard`
- Commit message style is conventional commits; use e.g.
  `fix(enrichment): block SSRF in WebFetch via is_safe_fetch_url + manual redirects (SEC-02)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Reject non-public URLs before fetching

In `apps/api/app/enrichment/sources/web_fetch.py`, import the guard at the top
with the other imports:

```python
from app.common.ssrf import is_safe_fetch_url
```

Then, inside `WebFetch.fetch`, **after** the existing scheme/host validation and
**before** the cache lookup and the HTTP request, add:

```python
        # SSRF guard: refuse URLs whose host resolves to a private/internal IP
        # (loopback, link-local incl. 169.254.169.254 metadata, RFC1918, etc.).
        # lead.website is user-controlled, so this MUST run on every fetch.
        if not is_safe_fetch_url(url):
            log.warning("source.web_fetch.blocked_ssrf", url=url)
            return SourceResult(source=self.name, query=url, error="blocked: non-public host")
```

**Verify**: `grep -n "is_safe_fetch_url" apps/api/app/enrichment/sources/web_fetch.py`
→ at least 2 matches (the import and the call).

### Step 2: Stop auto-following redirects; re-validate each hop

A 200-OK from a public host can still `301/302` to an internal host. Disable
httpx auto-redirects and follow them manually, re-validating each target host.

Replace the request block:

```python
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, max_redirects=3) as client:
                resp = await client.get(url, headers=headers)
        except httpx.TimeoutException as e:
            return SourceResult(source=self.name, query=url, error=f"timeout: {e}")
        except httpx.HTTPError as e:
            return SourceResult(source=self.name, query=url, error=f"http: {e}")
```

with a manual redirect loop (note `follow_redirects=False`):

```python
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
                current_url = url
                resp = await client.get(current_url, headers=headers)
                redirects = 0
                while resp.is_redirect and redirects < 3:
                    location = resp.headers.get("location")
                    if not location:
                        break
                    next_url = str(resp.next_request.url) if resp.next_request else location
                    # Re-validate every redirect target — defeats DNS/redirect rebinding.
                    if not is_safe_fetch_url(next_url):
                        log.warning("source.web_fetch.blocked_ssrf_redirect", url=next_url)
                        return SourceResult(source=self.name, query=url, error="blocked: redirect to non-public host")
                    current_url = next_url
                    resp = await client.get(current_url, headers=headers)
                    redirects += 1
        except httpx.TimeoutException as e:
            return SourceResult(source=self.name, query=url, error=f"timeout: {e}")
        except httpx.HTTPError as e:
            return SourceResult(source=self.name, query=url, error=f"http: {e}")
```

Leave the rest of the method (status check, body cap, HTML strip, title extract,
cache set, return) unchanged. The existing `items=[{"url": str(resp.url), ...}]`
still records the final URL correctly.

**Verify**: `grep -n "follow_redirects" apps/api/app/enrichment/sources/web_fetch.py`
→ shows `follow_redirects=False` (no `=True` remaining).

### Step 3: Add the regression test

Create `apps/api/tests/test_web_fetch_ssrf.py`. It must cover: (a) the guard's own
logic, (b) `WebFetch.fetch` refuses a blocked URL **without** making an HTTP
request, and (c) a public URL still succeeds. Use `respx` to assert HTTP behavior
and `monkeypatch` to control DNS resolution deterministically (do NOT depend on
real DNS in tests).

Target shape (adapt to the real `SourceResult` field names — confirm against
`app/enrichment/sources/base.py`):

```python
"""SEC-02 regression: WebFetch must not fetch private/internal URLs (SSRF)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.common import ssrf
from app.enrichment.sources.web_fetch import WebFetch


def test_is_safe_fetch_url_rejects_internal(monkeypatch):
    # Deterministic: pretend every host resolves to a private IP.
    monkeypatch.setattr(ssrf, "is_public_host", lambda host: False)
    assert ssrf.is_safe_fetch_url("http://169.254.169.254/latest/meta-data/") is False
    assert ssrf.is_safe_fetch_url("http://localhost:8000/admin") is False
    # Scheme guard is independent of DNS:
    assert ssrf.is_safe_fetch_url("file:///etc/passwd") is False


@pytest.mark.asyncio
async def test_web_fetch_blocks_internal_url_without_request(monkeypatch):
    # Force the host to look private; assert NO HTTP call is attempted.
    monkeypatch.setattr(
        "app.enrichment.sources.web_fetch.is_safe_fetch_url", lambda url: False
    )
    with respx.mock:
        route = respx.get("http://169.254.169.254/latest/meta-data/").mock(
            return_value=httpx.Response(200, text="SECRET")
        )
        result = await WebFetch().fetch(
            "http://169.254.169.254/latest/meta-data/", use_cache=False
        )
    assert route.called is False, "blocked URL must never be requested"
    assert result.error and "blocked" in result.error
    assert not result.items


@pytest.mark.asyncio
async def test_web_fetch_allows_public_url(monkeypatch):
    monkeypatch.setattr(
        "app.enrichment.sources.web_fetch.is_safe_fetch_url", lambda url: True
    )
    with respx.mock:
        respx.get("https://example.com/").mock(
            return_value=httpx.Response(
                200, text="<title>Hi</title><p>hello world</p>"
            )
        )
        result = await WebFetch().fetch("https://example.com/", use_cache=False)
    assert result.error is None
    assert result.items, "a public URL should return scraped items"
```

Notes for the executor:
- Patch the name **as imported into `web_fetch`** (`app.enrichment.sources.web_fetch.is_safe_fetch_url`),
  not `app.common.ssrf.is_safe_fetch_url`, in the `WebFetch` tests — otherwise the
  already-imported reference won't be patched.
- If `SourceResult` exposes the error differently (e.g. a method or a different
  field name), adjust the assertions to the real shape. Do not change production
  code to fit the test.
- If `respx` import fails, it is a declared dev dependency — run via
  `uv run pytest` (which uses the dev group), not bare `pytest`.

**Verify**: `cd apps/api && uv run pytest tests/test_web_fetch_ssrf.py -q` → 3 passed.

## Test plan

- New file `apps/api/tests/test_web_fetch_ssrf.py`, three tests:
  1. `test_is_safe_fetch_url_rejects_internal` — guard logic (private host + bad scheme).
  2. `test_web_fetch_blocks_internal_url_without_request` — the SEC-02 regression:
     a metadata URL is refused and **no HTTP request is made** (`route.called is False`).
  3. `test_web_fetch_allows_public_url` — a public URL still scrapes successfully
     (proves the guard didn't break the happy path).
- Structural pattern: existing enrichment-source tests that use `respx` (search
  `tests/` for `respx`); mirror their mock setup.
- Verification: `cd apps/api && uv run pytest tests/test_web_fetch_ssrf.py -q` → 3 passed.

## Done criteria

ALL must hold:

- [ ] `grep -n "is_safe_fetch_url" apps/api/app/enrichment/sources/web_fetch.py` → ≥2 matches
- [ ] `grep -n "follow_redirects=True" apps/api/app/enrichment/sources/web_fetch.py` → no matches
- [ ] `cd apps/api && uv run pytest tests/test_web_fetch_ssrf.py -q` → 3 passed
- [ ] `cd apps/api && uv run pytest tests/ -q -k "enrichment or web_fetch or source"` → all pass (no regression)
- [ ] `cd apps/api && uv run ruff check app/enrichment/sources/web_fetch.py tests/test_web_fetch_ssrf.py` → exit 0
- [ ] `cd apps/api && uv run mypy app/enrichment/sources/web_fetch.py` → exit 0
- [ ] Only the two in-scope files are modified (`git status`)
- [ ] `plans/README.md` status row for 002 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- `WebFetch.fetch` or `is_safe_fetch_url` does not match the "Current state"
  excerpts (the code drifted since 2026-06-11).
- `resp.is_redirect` / `resp.next_request` are not available on the installed
  httpx version — check `httpx.__version__` (pyproject pins `httpx>=0.28.1`, which
  has them). If the API differs, report rather than guessing a redirect API.
- The "allows public URL" test cannot pass even with the guard patched to `True`
  (means Step 2 broke normal fetching) — investigate Step 2, do not delete the test.
- You find a legitimate reason `WebFetch` must reach a private host (there is none
  for company-website scraping) — report instead of weakening the guard.

## Maintenance notes

- **Follow-up (out of scope here)**: `apps/api/app/enrichment/sources/rss_feed.py`
  fetches user-influenced feed URLs with the same exposure. The same
  `is_safe_fetch_url` guard should be applied there in a separate change. Flag this
  in your report.
- A stricter future hardening is to also pin the resolved IP and connect to it
  directly (full DNS-rebinding defense), but the manual-redirect re-validation in
  Step 2 closes the practical exploit path and is sufficient for this plan.
- Reviewer should confirm: no HTTP request is issued for a blocked URL (the test
  asserts `route.called is False`), and redirects are no longer auto-followed.
