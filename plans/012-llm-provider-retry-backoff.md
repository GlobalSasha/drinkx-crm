# Plan 012: Add a bounded retry with backoff on transient LLM errors before falling through to a pricier provider

> **Executor instructions**: Follow step by step; run every verification command.
> Honor STOP conditions. Update plan 012's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/enrichment/providers`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW (adds ≤1 retry with a short sleep; worst case slightly slower on a genuinely-down primary)
- **Depends on**: none
- **Category**: perf (cost/latency)
- **Planned at**: commit `9e93b16`, 2026-07-01

## Why this matters

On any `LLMError` the provider factory logs and **immediately** moves to the next
provider in the chain `[mimo, anthropic, gemini, deepseek]`. A transient `429`/`5xx`
on the cheap primary (MiMo) therefore needlessly escalates traffic to the pricier,
slower fallbacks (Anthropic/Gemini), inflating cost and latency and masking the
primary's real health. A single bounded retry with a short backoff on *transient*
statuses (429 / 5xx / timeout) — before falling through — fixes this cheaply.

## Current state

`apps/api/app/enrichment/providers/factory.py` — the fallback loop:
```python
        except LLMError as e:                       # line 94
            duration_ms = int((time.perf_counter() - attempt_start) * 1000)
            reason = f"{type(e).__name__}({e.status or '-'}): {str(e)[:120]}"
            log.warning("llm.fallback", provider=provider_name, reason=reason, ...)
            attempts.append((provider_name, reason))
            continue                                 # → next provider, no retry
```
- `LLMError` carries a `.status` attribute (used in the reason string) — the base
  error hierarchy is in `apps/api/app/enrichment/providers/base.py` (rate-limit /
  auth / server subclasses per the audit). Read it to see the exact classes and
  whether there's an `LLMRateLimitError` / `LLMServerError` split.
- Each provider is a single `httpx.post` with no internal retry, e.g.
  `apps/api/app/enrichment/providers/deepseek.py:54`.
- No `tenacity`/`backoff` dependency is used (and none is needed — a tiny inline
  helper is enough; do NOT add a dependency).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/enrichment/providers/factory.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/enrichment/providers` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q tests/test_llm_provider_retry.py` | all pass |

## Scope

**In scope:**
- `apps/api/app/enrichment/providers/factory.py`
- `apps/api/tests/test_llm_provider_retry.py` (create)

**Out of scope:**
- Individual provider modules (`mimo.py`, `deepseek.py`, …) — the retry belongs in
  the factory loop so it applies uniformly; don't add per-provider retry.
- Adding a retry library — use `asyncio.sleep` inline.
- Changing the fallback chain order or membership.

## Git workflow

- Branch: `advisor/012-llm-retry`
- One commit: `perf(enrichment): bounded retry+backoff on transient LLM errors before fallback (plan 012)`.

## Steps

### Step 1: Classify transient vs terminal errors

Determine which `LLMError`s are worth retrying: HTTP `429` and `5xx` and timeouts are
transient; `4xx` auth/validation (e.g. 401/400) are terminal (retrying wastes time).
Use the existing subclass split if present (e.g. `LLMRateLimitError`,
`LLMServerError`), else inspect `e.status`. Add a small predicate:
```python
def _is_transient(e: LLMError) -> bool:
    return e.status is None or e.status == 429 or 500 <= (e.status or 0) < 600
```

### Step 2: Retry once with backoff inside the per-provider attempt

Wrap the single `provider.complete(...)` call so that on a **transient** error it
retries up to `_MAX_RETRIES = 1` extra time after `await asyncio.sleep(_BACKOFF_S)`
(e.g. 0.5s, or exponential `0.5 * 2**attempt`), and only after exhausting retries
does it `continue` to the next provider. Terminal errors fall through immediately
(current behavior). Keep the existing `log.warning("llm.fallback", ...)` for the
final fall-through; add a `log.info("llm.retry", provider=..., attempt=...)` for the
retry itself.

Target shape (inside the existing `for provider_name, provider in chain:` loop):
```python
for retry in range(_MAX_RETRIES + 1):
    try:
        result = await provider.complete(...)
        ... # success path unchanged
        return result
    except LLMError as e:
        if _is_transient(e) and retry < _MAX_RETRIES:
            log.info("llm.retry", provider=provider_name, attempt=retry + 1, status=e.status)
            await asyncio.sleep(_BACKOFF_S * (2 ** retry))
            continue
        # terminal, or retries exhausted → fall through to next provider
        ...  # existing log.warning + attempts.append + break to next provider
```
Make sure `import asyncio` is present.

**Verify**: `grep -n "asyncio.sleep\|_MAX_RETRIES\|_is_transient" app/enrichment/providers/factory.py`
→ all present. `python -m py_compile` → 0.

### Step 3: Tests

Create `tests/test_llm_provider_retry.py` with a fake provider whose `complete`
raises a transient `LLMError` once then succeeds (assert only 1 provider used, 1
retry, no fall-through), and a terminal-error case (assert immediate fall-through, no
retry). Model after an existing provider/factory test (`grep -rln "factory\|LLMError" tests`).
Keep sleeps fast by monkeypatching `asyncio.sleep` or setting `_BACKOFF_S` small.

**Verify**: `cd apps/api && uv run pytest -q tests/test_llm_provider_retry.py` → all pass.

## Test plan

- New `tests/test_llm_provider_retry.py`, ~3 cases (transient-then-success, terminal
  immediate fall-through, all-retries-exhausted → next provider).
- Pattern: existing factory/provider test with fake providers.
- Verification: pytest command passes.

## Done criteria

- [ ] `python -m py_compile app/enrichment/providers/factory.py` → 0
- [ ] `uv run ruff check app/enrichment/providers` → 0
- [ ] `uv run pytest -q tests/test_llm_provider_retry.py` → all pass
- [ ] A transient error retries the **same** provider before any fallback (asserted in tests)
- [ ] No new dependency added (`git diff apps/api/pyproject.toml` empty)
- [ ] No files outside scope modified (`git status`)
- [ ] `plans/README.md` round-3 row for 012 updated

## STOP conditions

- Excerpts don't match live code (drift) — report.
- `LLMError` has no usable status/type to classify transient vs terminal — STOP and
  report; retrying blindly (incl. auth errors) is worse than the status quo.
- The factory is also used on a latency-critical synchronous path where an extra
  0.5–1s is unacceptable — if found, gate retries to the enrichment/agent task paths
  only and note it.

## Maintenance notes

- Keep `_MAX_RETRIES` at 1 and backoff short; this is a *transient-blip* smoother,
  not a resilience layer. More retries would delay legitimate fallback.
- If per-provider circuit-breaking is ever added, this retry becomes its inner loop.
