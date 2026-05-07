# Sprint 1.3 — AI Enrichment Report

**Closed on:** 2026-05-07
**Branch flow:** `sprint/1.3-llm-providers` → `hotfix/llm-timeout-error-reporting` → `sprint/1.3-d-budget-and-profile`, all merged into `main` and deployed to https://crm.drinkx.tech.

**Status:** ✅ Phases A + B + C + D + E shipped to production · ⏸ Phases F + G deferred.

---

## Scope vs original plan

Original Sprint 1.3 envelope from `04_NEXT_SPRINT.md`:
1. Provider abstraction (LLMProvider Protocol, MiMo / Anthropic / Gemini / DeepSeek, factory)
2. Sources (Brave + HH.ru + web_fetch with Redis cache)
3. Research Agent (orchestrator, `enrichment_runs` + Celery, `ResearchOutput`, WebSocket progress)
4. Knowledge Base + business profile
5. Cost control (pre-filter, rate limit, budget guard)
6. Web — enrichment UI
7. Tests

What was delivered, mapped to phases:

| Phase | Scope | Status |
|---|---|---|
| A | LLMProvider Protocol + 4 providers + factory + ResearchOutput + 15 tests | ✅ Live |
| B | Brave / HH.ru / web_fetch sources + Redis 24h cache + 17 tests | ✅ Live |
| C | Orchestrator + `enrichment_runs` migration `0003` + REST endpoints + 14 tests | ✅ Live |
| E | AI Brief tab redesign + trigger + polling + per-lead rate limit + 2 tests | ✅ Live |
| D | DrinkX profile injection + daily budget + concurrency cap + 11 tests | ✅ Live |
| F | Knowledge Base markdown library (tag-matched grounding) | ⏸ Deferred |
| G | Celery worker for enrichment + WebSocket real-time progress | ⏸ Deferred |

**Total:** 6 commits on main, ~4500 lines, 59 new tests.

---

## What shipped (in order)

### Commit `67f9c6b` — Phase A: LLM Provider abstraction
- `app/enrichment/providers/{base,mimo,anthropic,gemini,deepseek,factory}.py`
- `LLMProvider` Protocol with `TaskType` enum (Flash vs Pro split per ADR-018)
- MiMo (OpenAI-compatible, `api-key:` header per CLAUDE.md), Anthropic Messages API, Gemini v1beta REST, DeepSeek (OpenAI-compatible)
- `complete_with_fallback()` walks `LLM_FALLBACK_CHAIN` on rate-limit / auth-error / 5xx
- `ResearchOutput` Pydantic with fallback defaults everywhere — never raises on missing AI fields (PRD §7.2 anti-pattern #7)

### Commit `2071fc1` — Phase B: Data sources
- `app/enrichment/sources/{base,brave,hh,web_fetch,cache}.py`
- Uniform `SourceResult` shape (source, items, cached, elapsed_ms, error)
- 24h Redis cache: `enrich:{source}:{sha1(query)[:16]}`
- All sources fail-soft: errors return `SourceResult(error=...)`, never raise
- 17 tests via `httpx.MockTransport` + monkey-patched cache

### Commit `802df7d` — Phase C: Research Agent + persistence
- Migration `0003_enrichment_runs` (status, provider/model, tokens, cost, duration, sources_used, result_json, started_at/finished_at, indexes)
- `EnrichmentRun` ORM model + `EnrichmentRunOut` / `EnrichmentTriggerOut` DTOs
- Orchestrator: query builder → `asyncio.gather` Brave×3 + HH.ru + optional WebFetch → synthesis via `complete_with_fallback(research_synthesis)` → save to `lead.ai_data` + run row
- `POST /leads/{id}/enrichment` (202 + `BackgroundTasks`), `GET /latest`, `GET` list
- Orchestrator never raises — failures write `status=failed` with `error` captured
- 14 tests

### Commit `83f4974` — Phase E: Frontend AI Brief tab + per-lead rate limit
- Backend: `EnrichmentAlreadyRunning` exception → 409 with in-flight `run_id`
- Frontend: `AIBriefTab` component (between Сделка and Контакты), `useLatestEnrichment` polls every 2s while status=running, `useTriggerEnrichment` mutation
- TS types: `ResearchOutput`, `DecisionMakerHint`, `EnrichmentRun`, `EnrichmentTriggerResponse`
- BriefDrawer "Запустить enrichment" affordance when `ai_data` empty

### Commit `810a4ba` — Hotfix: LLM timeout + error chain
- Default `timeout_seconds` 30s → **90s** (synthesis with multi-KB prompts was getting killed)
- `complete_with_fallback` now collects per-attempt reasons and surfaces the full chain in the raised error — operators no longer see misleading `DEEPSEEK_API_KEY not set` when MiMo silently timed out two providers earlier.

### Commit `0826eb9` — Hotfix: MiMo reasoning + tighter prompt
- MiMo payload: `reasoning_effort: "minimal"` + `thinking: {type: "disabled"}` + `stream: false` (defensive — unknown fields are ignored by OpenAI-compat servers)
- Synthesis prompt got explicit rules: single JSON object, no markdown, no preamble, "не выдумывай decision_maker_hints"
- Schema spelled out inline; `company_profile` capped at 2 sentences

### Commit `2992c97` — Hotfix: permissive schema + business prompt + redesigned UI
- **Backend schema:** loosened `role` / `confidence` / `urgency` from `Literal[...]` to plain `str`. LLMs returned Russian values like `"закупки"` for `role` → Pydantic ValidationError → fallback dumped raw JSON into `notes` → frontend rendered as wall of text + `fit_score=0`. Now permissive; UI maps known canonical values.
- `formats` / `coffee_signals` accept `str | list[str]`.
- **Synthesis prompt:** explicit forbidden jargon list (`ритейлер`, `email-рассылки`, `B2B`, `ROI`, `кофейные технологии`, `кофепойнты`, `стейкхолдеры`, `ICP`, `закупочная команда`, `operational excellence`); business-tone Russian as written by an account manager.
- **AI Brief tab redesign** (via frontend-design skill): hero band with company_profile + 96px fit_score badge, white panels on canvas, coffee signals in accent panel (the thesis), growth/risk as balance sheet, decision-maker cards with avatar + role + confidence, numbered next-step list. `asList`/`asText` helpers absorb LLM shape variations. Failure-fallback (raw JSON in notes) hidden behind `<details>` instead of dumped into the body.

### Commit `6715f8e` — Phase D: Profile + budget + concurrency
- `config/drinkx_profile.yaml` — product, ICP, fit_score anchors, common objections, signals to extract; rendered into synthesis system prompt for grounding
- `app/enrichment/profile.py` — `lru_cache`d YAML loader + `render_profile_for_prompt()`
- `app/enrichment/budget.py` — Redis-backed daily spend counter `ai_budget:{workspace_id}:{YYYY-MM-DD}`; cap = `ai_monthly_budget_usd / 30`; `add_to_daily_spend()` called on every succeeded run; reads/writes are fail-soft
- `app/enrichment/concurrency.py` — `count_running_for_workspace()` via JOIN on `leads.workspace_id`; cap = `ai_max_parallel_jobs`
- `services.trigger_enrichment` raises `EnrichmentConcurrencyLimit` / `EnrichmentBudgetExceeded`; routers map both → **HTTP 429** with Russian detail
- 11 tests across profile / budget / routes
- Added `pyyaml` to `pyproject.toml`

---

## Decisions made during the sprint

- **ADR-018** was implemented (MiMo primary, fallback chain). Confirmed working in prod: MiMo Flash answers `say ok` in 2s with `reasoning_tokens=0`. Anthropic confirmed **403 forbidden** from Russian VPS IP — kept in the chain but it's effectively dead until VPN; documented as known limitation.
- **Permissive schema over strict Literal** — when an LLM returns a free-form value, the right move is to accept it and let the UI normalize, not to fail the whole research run. The Literal was a leak of API-side discipline into a probabilistic boundary.
- **Profile as system-prompt grounding, not full RAG** — for Phase D we inlined a ~800-char DrinkX brief into every synthesis call. Phase F's KB markdown library will replace this when segment-specific playbooks land, but the inlined profile already lifts brief quality.
- **`BackgroundTasks` over Celery for now** — the orchestrator runs in-process via FastAPI `BackgroundTasks` against a fresh DB session. Celery + WebSocket land together in Phase G when we have a multi-replica deployment that needs out-of-process workers.
- **Daily budget cap = monthly / 30** — simple and good enough for a small team. The Redis counter has a 36h TTL (covers timezone slack).

---

## Production state at sprint close

| Concern | State |
|---|---|
| MiMo primary | ✅ Working, ~2s for `say ok`, slower for full synthesis |
| Anthropic fallback | ⚠ Always 403 from RU IP (provider-side region block) |
| Gemini fallback | ⚠ No API key configured in prod |
| DeepSeek fallback | ⚠ No API key configured in prod (intentional per user) |
| Brave Search | ✅ Key set, results cached for 24h |
| HH.ru | ✅ No-auth public API |
| web_fetch | ✅ 800KB cap, strip script/style, 50K text truncation |
| Redis cache | ✅ Active for sources + budget counter |
| `enrichment_runs` table | ✅ Live; row per trigger with cost / duration metrics |
| AI Brief UI | ✅ Live in Lead Card |
| Per-lead 1-running rate limit | ✅ 409 |
| Workspace concurrency cap | ✅ 5 jobs / 429 |
| Daily AI budget | ✅ ~$6.66/day default ($200 monthly / 30) |
| 216 leads in pool | ✅ a.hvastunov@gmail.com workspace |

## Tests on `main`

- 17 unit tests in `test_0002_b2b_models.py` — pass without DB
- 15 LLM provider tests — pass without DB
- 17 source tests — pass without DB
- 14 orchestrator tests — pass without DB (mocked sources/providers)
- 5 enrichment-route tests — pass without DB (mocked services)
- 3 profile tests — pass without DB
- 5 budget tests — pass without DB
- ~85 PG-gated integration tests — skip locally, run on prod / future CI

**Total: ~76 unit tests stay green on `main`.**

---

## Known issues / risks

1. **Anthropic from RU is dead** — every fallback walk pays the round-trip latency to get a 403 before falling through to Gemini/DeepSeek. Cheap to fix (drop Anthropic from default chain, add to opt-in chain), but not done yet.
2. **No retry on transient timeout** — if MiMo blips once, we don't retry within the same provider before falling through. Could be added with `httpx.AsyncHTTPTransport(retries=...)`.
3. **No Celery / WebSocket** — UI polls every 2s while a run is in flight. Acceptable for low concurrency; will need replacement at scale.
4. **Profile YAML is static** — no admin UI, no per-workspace override. Phase F's KB system or a future admin page solves this.
5. **`datetime.utcnow()` deprecation warning** in `budget.py` — cosmetic on Python 3.14, not on 3.12. Trivial fix when convenient.
6. **`fit_score` field on `Lead`** — orchestrator updates it from `ResearchOutput.fit_score` but the UI's manual scoring tab can also set it. Last-writer-wins; no conflict resolution. Acceptable — manager always overrides AI on the same field semantics.

---

## Files changed (cumulative across the sprint)

```
apps/api/app/enrichment/
  __init__.py
  api_schemas.py
  models.py
  orchestrator.py
  routers.py
  schemas.py
  services.py
  budget.py            (Phase D)
  concurrency.py       (Phase D)
  profile.py           (Phase D)
  providers/
    __init__.py
    base.py
    factory.py
    mimo.py
    anthropic.py
    gemini.py
    deepseek.py
  sources/
    __init__.py
    base.py
    brave.py
    hh.py
    web_fetch.py
    cache.py
apps/api/alembic/versions/20260506_0003_enrichment_runs.py
apps/api/config/drinkx_profile.yaml
apps/api/tests/
  test_llm_providers.py
  test_sources.py
  test_enrichment_orchestrator.py
  test_enrichment_routes.py
  test_enrichment_profile.py     (Phase D)
  test_enrichment_budget.py      (Phase D)
apps/api/pyproject.toml          (added pyyaml)
apps/api/app/main.py             (registered enrichment router)
apps/api/alembic/env.py          (registered EnrichmentRun model)
apps/web/components/lead-card/AIBriefTab.tsx
apps/web/components/pipeline/BriefDrawer.tsx (enrichment CTA)
apps/web/components/lead-card/LeadCard.tsx   (added AI Brief tab)
apps/web/lib/types.ts            (added enrichment + ResearchOutput types)
apps/web/lib/hooks/use-enrichment.ts
AUTOPILOT.md                      (1.3.1, 1.3.2, 1.3.3, 1.3.4, 1.3.5, 1.3.6 ticked)
docs/brain/03_DECISIONS.md        (ADR-018)
```

---

## Deferred to follow-on phases

### Phase F — Knowledge Base library
- `apps/api/knowledge/drinkx/*.md` — playbooks: `playbook_horeca.md`, `playbook_qsr.md`, `playbook_gas_stations.md`, `objections_common.md`, `objections_pricing.md`, `case_studies.md`
- Each MD file with YAML frontmatter (`tags: [horeca, mid_chain]`, `priority: 1`)
- Loader at API startup: reads all files into Redis under `kb:{slug}` key, watches for filesystem changes during dev
- Tag matcher selects relevant files for the synthesis prompt based on `lead.segment` + `lead.deal_type`
- Estimated 1 subagent dispatch.

### Phase G — Celery + WebSocket
- Move orchestrator from FastAPI `BackgroundTasks` to Celery worker (already a service in `infra/production/docker-compose.yml`, currently commented out)
- Add `celery_app.py` + `tasks.py` (one task: `run_enrichment_task(run_id)`)
- WebSocket endpoint `/ws/{user_id}` (Redis pub/sub) — orchestrator publishes `enrichment.started`, `enrichment.source_done`, `enrichment.completed`, `enrichment.failed`
- Frontend swaps polling for WebSocket subscription
- Estimated 2 subagent dispatches + infra config update.

---

## Next sprint

See `docs/brain/04_NEXT_SPRINT.md` — **Sprint 1.4 — Daily Plan generator**.
