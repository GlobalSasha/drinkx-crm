# Sprint 4.0 — LLM Cost Counter (admin) — Design

**Date:** 2026-05-20
**Status:** Approved (design)
**Goal:** Give admins a single place to see how much money the CRM spends on LLM calls — total and broken down by provider — filterable by period.

---

## Problem

Today LLM spend is only partially visible:

- `EnrichmentRun.cost_usd` persists per-enrichment cost, but it is **never displayed** — the Lead Card reads only `run.provider` (`apps/web/components/lead-card/DealAndAITab.tsx:218`). Cost/token columns are written "to the drawer".
- `app/enrichment/budget.py` tracks daily spend per workspace in **Redis with a 36h TTL** — ephemeral, no history, not broken down by provider.
- Non-enrichment LLM calls (Блейк sales coach, daily plan, inbox prefilter) are **not tracked for cost at all**.

There is no persistent, queryable ledger of LLM spend across the whole CRM.

## What we are building

An admin-only counter that answers: **"How much money has the CRM spent on each connected LLM, and in total, over a chosen period?"**

In scope:
- A persistent per-call cost ledger (`llm_usage`).
- Recording at the single LLM chokepoint (`complete_with_fallback`).
- One admin API endpoint returning total + per-provider breakdown for a period.
- A `Settings → Расходы` section: period toggle + total figure + per-provider list.

Explicitly **out of scope** (YAGNI — data is captured so these can be added later without backfill):
- By-feature breakdown.
- 6-month trend / charts.
- Per-manager attribution.
- A central pricing table (providers already compute `cost_usd`).

---

## Architecture & data flow

`complete_with_fallback` is the single chokepoint for **every** LLM call (6 call sites: enrichment orchestrator ×2, lead_agent runner ×2, daily_plan, inbox message_tasks, plus scheduled/jobs). Recording there captures everything automatically — current and future call sites.

```
call-site → complete_with_fallback(system, user, task_type, workspace_id=ws)
              ├─ provider.complete() → CompletionResult(provider, model, tokens, cost_usd)
              ├─ on success: record_llm_usage(ws, task_type, result)   ← best-effort
              └─ return result
```

**Best-effort recording.** `record_llm_usage` is fire-and-forget: it must never block the LLM response and must never raise into the LLM path. On any DB/telemetry failure it logs `log.warning("llm_usage.record_failed", ...)` and the `CompletionResult` is still returned. Rationale: cost telemetry is observability, not a correctness dependency of enrichment / Блейк / daily plan.

**Cost source.** We trust `CompletionResult.cost_usd`. Each provider already computes it from token counts × hard-coded per-token pricing (`apps/api/app/enrichment/providers/{mimo,anthropic,gemini,deepseek}.py`). No separate pricing table — if prices change, they are edited where they already live.

**workspace_id propagation.** `complete_with_fallback` gains an optional `workspace_id: uuid.UUID | None = None` parameter. All 6 call sites already have `workspace_id` in scope and pass it. If `None` (defensive), the call still succeeds but is recorded with a null workspace (or skipped — see Decisions); we pass it everywhere so this should not happen in practice.

**Avoiding circular imports.** `app/enrichment/providers/factory.py` imports `record_llm_usage` lazily (inside the function body), since `app/llm_usage/` depends on the DB/session layer.

---

## Data model

New domain `app/llm_usage/` (package-per-domain convention). One row per LLM call. Low volume (~thousands of rows/month), kept indefinitely — no rollups.

```python
# app/llm_usage/models.py
class LlmUsage(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "llm_usage"

    workspace_id: Mapped[uuid.UUID] = mapped_column(index=True)   # FK to workspace
    task_type:    Mapped[str] = mapped_column(String(40))         # raw TaskType.value; stored for future breakdowns, not shown in UI
    provider:     Mapped[str] = mapped_column(String(40))         # "mimo" | "anthropic" | "gemini" | "deepseek"
    model:        Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_tokens:     Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd:     Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    # created_at (from TimestampedMixin) is the period axis
```

**Index:** `(workspace_id, created_at)` covers period-filtered aggregation.

**EnrichmentRun cleanup (Variant A — single ledger, no duplication).** Since the factory now records enrichment calls into `llm_usage`, the cost columns on `EnrichmentRun` become redundant. Remove them:
- Drop `cost_usd`, `prompt_tokens`, `completion_tokens` from `EnrichmentRun` (Alembic migration).
- Remove the writes in `apps/api/app/enrichment/orchestrator.py` (~lines 809–811).
- Remove the fields from `EnrichmentRunOut` (`app/enrichment/api_schemas.py:19–21`) and from `apps/web/lib/types.ts:438–440`.
- **Keep** `EnrichmentRun.provider` — the Lead Card displays it.
- `budget.py` is untouched: it reads `completion.cost_usd` directly, not from the run row.

**Migration discipline (lesson from Sprint 3.7):** revision id MUST be slug-style (e.g. `0032_llm_usage_table`), not timestamp-prefixed. Self-review step: `grep "^revision =" ` the latest existing migration + run `alembic heads` before commit.

---

## API

One admin-only endpoint (gated like `/audit`: `me.role == "admin"`).

```
GET /admin/llm-costs?period=this_month
```

`period` ∈ `this_month` | `last_month` | `all` (default `this_month`). Month boundaries computed in UTC (consistent with the Celery beat clock).

Response:
```jsonc
{
  "period": "this_month",
  "total_usd": 47.82,
  "by_provider": [
    { "provider": "mimo",      "cost_usd": 40.20, "calls": 980 },
    { "provider": "anthropic", "cost_usd": 5.10,  "calls": 42  },
    { "provider": "gemini",    "cost_usd": 1.80,  "calls": 30  },
    { "provider": "deepseek",  "cost_usd": 0.72,  "calls": 12  }
  ]
}
```

- Aggregation: a single `SELECT provider, SUM(cost_usd), COUNT(*) ... WHERE workspace_id=? AND created_at IN [period] GROUP BY provider`. `total_usd` is the sum across rows.
- All four known providers are always present in `by_provider` (zero-filled if no calls in the period) so admins can see a connected-but-idle provider. Provider list comes from `llm_fallback_chain` / the provider registry.
- Scope: the admin's workspace (single shared workspace today).

**Backend files (new domain `app/llm_usage/`):**
- `models.py` — `LlmUsage`.
- `service.py` — `record_llm_usage(db, *, workspace_id, task_type, result)`; best-effort wrapper used by the factory.
- `repositories.py` — insert + period-filtered `GROUP BY provider` aggregate; period→date-range helper.
- `schemas.py` — `LlmCostsOut`, `ProviderCostOut`.
- `routers.py` — `GET /admin/llm-costs`, admin guard.
- Register router in the app; register model in `app/scheduled/celery_app.py` side-effect imports (the worker process records usage too).

---

## UI

`Settings → Расходы`, admin-only (new `SectionKey: "costs"` in `apps/web/app/(app)/settings/page.tsx`, new `components/settings/CostsSection.tsx`).

Layout (no charts, no tables-by-feature):
- Period toggle: **Этот месяц / Прошлый месяц / Всё время**.
- Large headline: **«Всего на AI: $47.82»** for the selected period.
- Below: a list of providers, each row = provider name + cost + call count. Zero-cost providers shown muted.

Data via a TanStack Query hook `useLlmCosts(period)` hitting `GET /admin/llm-costs`. Section is hidden / redirects for non-admins, matching the existing admin-gating pattern (`app/(app)/audit/page.tsx`).

---

## Testing

Backend (mock-stubbed sqlalchemy pattern, per `tests/test_webforms.py`):
- `record_llm_usage` inserts a row with the right fields from a `CompletionResult`.
- `record_llm_usage` swallows DB errors (best-effort) — patched session that raises → no exception propagates, warning logged.
- Period→date-range helper: `this_month` / `last_month` / `all` produce correct UTC bounds.
- Aggregate repository: given fake rows, returns correct per-provider sums + total; zero-fills missing providers.
- `complete_with_fallback` calls `record_llm_usage` on success with the passed `workspace_id` and the result's provider/cost (patched).

Frontend: typecheck + lint + `pnpm build` (App-Router routing touched via new settings section). Manual: log in as admin, open Settings → Расходы, toggle periods.

---

## Decisions / open questions resolved

1. **Record in factory** (single chokepoint) — chosen over per-call-site helper and Redis-only aggregates.
2. **By provider + total only** — no by-feature, no trend (`task_type` still stored for future use).
3. **Period filter:** this_month / last_month / all, UTC boundaries.
4. **No duplication (Variant A):** `llm_usage` is the single cost ledger; redundant cost columns dropped from `EnrichmentRun`.
5. **`workspace_id=None` fallback:** pass `workspace_id` from all call sites; recording is best-effort so a missing value never breaks the LLM path.
