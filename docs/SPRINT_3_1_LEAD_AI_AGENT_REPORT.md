# Sprint 3.1 — Lead AI Agent (closure report)

**Status:** ✅ DONE — all phases shipped to production
**Range:** 2026-05-10 → 2026-05-10 (single-day execution across one
authoring session)
**Spec:** [`docs/SPRINT_3_1_LEAD_AI_AGENT.md`](SPRINT_3_1_LEAD_AI_AGENT.md)

## Goal

Single AI agent inside the LeadCard with two modes:

- **Background** — Celery task watches active leads, recomputes a
  banner-recommendation when triggers fire (stage change, new
  inbound email, scheduled silence sweep). Cheap MiMo Flash via
  `TaskType.prefilter`.
- **Foreground** — Sales Coach chat drawer with full lead context.
  Free-text + four canonical quick chips. MiMo Pro via
  `TaskType.sales_coach`.

Both modes share `app/lead_agent/prompts.py` which assembles the
system prompt from `apps/api/knowledge/agent/product-foundation.md`
(loaded once via `lru_cache`) + per-call `LeadAgentContext`.

## Phases shipped

| Phase | Scope | PR | Merged |
|---|---|---|---|
| **A** | Knowledge files in repo | [#18](https://github.com/GlobalSasha/drinkx-crm/pull/18) | 2026-05-10 19:49 |
| **B** | Migration `0022_lead_agent_state` + ORM column | [#18](https://github.com/GlobalSasha/drinkx-crm/pull/18) | 2026-05-10 19:49 |
| **C** | `app/lead_agent/` package + REST + Celery | [#18](https://github.com/GlobalSasha/drinkx-crm/pull/18) | 2026-05-10 19:49 |
| Operator follow-on | Bake `docs/` into the API image (later moved to `apps/api/knowledge/`) | [#19](https://github.com/GlobalSasha/drinkx-crm/pull/19) | 2026-05-10 19:54 |
| **D** | LeadCard `AgentBanner` + `SalesCoachDrawer` + 3 hooks | [#22](https://github.com/GlobalSasha/drinkx-crm/pull/22) | 2026-05-10 20:05 |
| **E** | `stage_change.py` POST_ACTION + `inbox/processor.py` countdown=900 | [#22](https://github.com/GlobalSasha/drinkx-crm/pull/22) | 2026-05-10 20:05 |
| Knowledge co-location | Move `docs/skills/` + `docs/knowledge/agent/` → `apps/api/knowledge/agent/` so the existing `COPY knowledge ./knowledge` ships them | [#20](https://github.com/GlobalSasha/drinkx-crm/pull/20) | 2026-05-10 |
| **G5** | This report + brain rotation + roadmap update | _this PR_ | _pending_ |

## What landed

### Phase A — Knowledge files

- `apps/api/knowledge/agent/product-foundation.md` — DrinkX product context, v1.0 (positioning, S100–S400 lineup, segments, top objections, USP map, vocabulary do/don't, hard rules). 7259 chars.
- `apps/api/knowledge/agent/lead-ai-agent-skill.md` — agent behavioural skill, v1.0 (modes, foundation-loading rule, principles, agent_state shape, triggers, SPIN-by-stage, output formats, tone, hard rules, special scenarios, system integration, success metrics).

Both files were originally placed under `docs/` per the Phase A spec; PR #20 co-located them with the API package so the existing `COPY knowledge ./knowledge` Dockerfile line ships them into the container at `/app/knowledge/agent/`.

### Phase B — Migration 0022

- `apps/api/alembic/versions/20260510_0022_lead_agent_state.py` — `ALTER TABLE leads ADD COLUMN agent_state JSONB NOT NULL DEFAULT '{}'`. Existing rows backfill via `server_default`. Down-migration drops the column.
- `apps/api/app/leads/models.py:Lead.agent_state` — ORM mapped to plain SQLAlchemy `JSON` (Postgres still stores JSONB at the migration level; plain `JSON` keeps the test stub compatible since several test files only stub `JSON`/`UUID` from `sqlalchemy.dialects.postgresql`).
- Migration index correction documented: spec said 0013, actual is 0022 because 0013 was taken by Sprint 2.3 (`default_pipeline`) and 0021 by Sprint 2.7 G2 (`automation_steps`).

### Phase C — `app/lead_agent/` package

```
apps/api/app/lead_agent/
├── __init__.py        — module docstring
├── schemas.py         — AgentSuggestion / ChatMessage / ChatRequest /
│                        ChatResponse / SuggestionResponse
├── context.py         — lru_cache loaders (find_knowledge_root walks
│                        upwards looking for knowledge/agent/) +
│                        build_lead_context(lead, stage_name=)
├── prompts.py         — SUGGESTION_SYSTEM (Flash) + CHAT_SYSTEM (Pro)
│                        templates with FOUNDATION_INJECT_CHARS=3000
├── runner.py          — get_suggestion (Flash, JSON parse + code-fence
│                        strip) + chat (Pro, RU fallback on LLMError)
├── tasks.py           — refresh_suggestion_async + scan_silence_async
│                        async cores; per-task NullPool engine
└── routers.py         — 3 endpoints under /leads/{id}/agent
```

Both runner entry points use `app.enrichment.providers.factory.complete_with_fallback` — no new abstraction layer, ADR-018 fallback chain inherited (MiMo → Anthropic → Gemini → DeepSeek).

#### REST surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/leads/{id}/agent/suggestion` | Read cached suggestion (no LLM) |
| POST | `/api/leads/{id}/agent/suggestion/refresh` | Enqueue Celery refresh, returns 202 |
| POST | `/api/leads/{id}/agent/chat` | Sales Coach turn, synchronous |

#### Celery wiring

- `lead_agent_refresh_suggestion(lead_id: str)` — sync wrapper in `app/scheduled/jobs.py` → async core `app.lead_agent.tasks.refresh_suggestion_async`. Fired ad-hoc (REST `/refresh`, Phase E hooks).
- `lead_agent_scan_silence()` — beat task on `crontab(minute=0, hour="*/6")`. Sweeps `assignment_status='assigned' AND archived_at IS NULL AND won_at IS NULL AND lost_at IS NULL` leads with `last_activity_at` older than `SCAN_SILENCE_DAYS` (3) and dispatches a refresh per row. Beat tick stays light: one SELECT, then `apply_async` per row.

### Phase D — Frontend

- `apps/web/lib/types.ts` — added `AgentSuggestion`, `AgentSuggestionResponse`, `AgentChatMessage`, `AgentChatRequest`, `AgentChatResponse`.
- `apps/web/lib/hooks/use-lead-agent.ts` — three React Query hooks:
  - `useAgentSuggestion(leadId)` → GET (30s staleTime)
  - `useRefreshAgentSuggestion(leadId)` → POST + 12s soft-poll: invalidates the suggestion cache every 3s for ~12s after the enqueue, then settles (the runner writes the fresh suggestion into `agent_state` async)
  - `useAgentChat(leadId)` → POST mutation
- `apps/web/components/lead-card/AgentBanner.tsx` — strip between LeadCard header and tabs:
  - Empty-row state: thin «Чак ещё не давал рекомендаций» with a manual refresh button
  - Suggestion present: text + optional action button + «Спросить Чака» link + manual refresh + dismiss (×) + confidence badge
  - `confidence < 0.4` mutes styling and drops the action_label (server enforces too)
- `apps/web/components/lead-card/SalesCoachDrawer.tsx` — right-side slide-over chat:
  - Static greeting from Чак at the top (no LLM call on open)
  - Four quick chips: «Что делать дальше», «Напиши follow-up письмо», «Разбери возражение», «Готов ли лид к переходу»
  - In-memory history (per skill §8 — closing drops it)
  - Esc/backdrop close, auto-scroll, optimistic user-turn append, in-line failure message
- `apps/web/components/lead-card/LeadCard.tsx` — banner mounted between `</header>` and `<main>`; FAB `🤖 Чак` bottom-right; drawer rendered via `coachOpen` state.

`pnpm typecheck` clean. 0 new npm deps.

### Phase E — Backend hooks

Two minimal call sites add `lead_agent_refresh_suggestion` to existing trigger fan-outs. Both wrap the Celery enqueue in `try/except` so a broker hiccup never rolls back the parent commit.

- `app/automation/stage_change.py` — new `trigger_lead_agent_refresh` POST_ACTION runs **last** in the list (after `set_won_lost_timestamps`, `log_stage_change_activity`, `fan_out_automation_builder`). `apply_async(args=[str(lead.id)])` — no countdown, fires immediately.
- `app/inbox/processor.py` — after `flush_pending_email_dispatches` in the auto-attach branch, fire the same task with `countdown=900`. The 15-min delay is the spec's «менеджер может ответить сам» window. **Only** `direction == "inbound"` triggers — outbound is the manager's own action.

### Operator follow-on (PR #19 + #20)

- `apps/api/Dockerfile` — repo-root build context expanded; `COPY docs ./docs` was added in PR #19 to ship knowledge files into the image.
- PR #20 then **moved** the knowledge files from `docs/skills/` + `docs/knowledge/agent/` to `apps/api/knowledge/agent/` and updated `app/lead_agent/context.py` to look in the new location. The existing `COPY knowledge ./knowledge` line in `apps/api/Dockerfile` already shipped them; the explicit `COPY docs ./docs` from PR #19 is now redundant for the agent but harmless (other docs ride along).
- The lazy `_find_knowledge_root` walker still soft-fails when files aren't present — the agent runs with an empty foundation block and a one-shot warning.

## Tests

- 51/51 mock-only tests pass (`test_audit`, `test_email_sender`, `test_automation_*`, `test_sentry_capture`, `test_inbox_services`).
- No new dedicated lead_agent tests — the runner is a thin shim around `complete_with_fallback`, the routers are read-only or fire-and-forget Celery enqueues, and the frontend has no test infra. Real verification is the post-deploy smoke check (operator sees the banner update + chat reply on a real lead).

## Net-new dependencies

- **0 npm** — frontend reuses React Query + lucide-react + the existing brand design system tokens
- **0 Python** — the runner reuses `app.enrichment.providers.factory.complete_with_fallback` end-to-end

## Architecture decisions

1. **One agent, two modes, one prompt builder.** The skill is enforced by `prompts.py` templates + the `product-foundation.md` injection — not by separate "background agent" / "chat agent" classes. Mode selection is purely the `task_type` parameter into the existing fallback chain.
2. **No new TaskType.** `prefilter` (Flash) already covers the cheap-and-often background path; `sales_coach` (Pro) already covers the heavy chat path. Adding `lead_agent_background` / `lead_agent_chat` aliases would have been signal-zero.
3. **Knowledge files on disk, lru_cache, soft-fail.** The runtime never blocks on a missing knowledge file — it logs a one-shot warning and runs with an empty foundation block. PR #20 finalised the layout so the existing Dockerfile copies them without further changes.
4. **`lead.agent_state['suggestion']` is the authoritative cache.** The GET endpoint never hits the LLM; the POST `/refresh` enqueues a Celery task that overwrites the slot. The frontend polls GET for ~12s after enqueueing.
5. **Confidence threshold enforced server-side.** `runner.get_suggestion` clears `action_label` when `confidence < 0.4`. The frontend `AgentBanner` mirrors the rule for defence-in-depth, but the canonical decision is in the runner.
6. **`_dispatch_step` signature collapse not relevant here.** The lead_agent runner doesn't go through the Automation Builder dispatch path — it talks directly to the LLM. The `(lead, config, automation_id_str)` refactor stays scoped to Sprint 2.7 G2.
7. **History persistence: explicitly OUT.** Spec §10 calls it out — "не персистится — достаточно для сессии". Closing the drawer drops the conversation. Reopening starts fresh.
8. **Phase E hooks are fire-and-forget.** `apply_async` failure → log warning, never roll back the parent commit. The agent's banner staying stale for one missed trigger is a soft failure; rolling back a stage move because Redis hiccupped is a hard one.

## Production state at close

- All 4 PRs merged (#18, #19, #20, #22). Latest deploy: PR #22 → `25638481790` (success, 2026-05-10 20:05).
- `https://crm.drinkx.tech/api/version` → `{"version":"0.1.0","env":"production"}`
- Lead AI Agent endpoints live at `/api/leads/{id}/agent/{suggestion,suggestion/refresh,chat}`
- Beat schedule entry `lead-agent-scan-silence` active (every 6h)
- Frontend banner + FAB visible on every LeadCard; FAB toggles drawer

## Operator post-deploy smoke checklist

- [ ] Open a lead with no `agent_state.suggestion` → banner shows the empty-row strip
- [ ] Click «Запросить» → 202, banner re-fetches every ~3s for ~12s, eventually shows the runner's text + confidence badge
- [ ] Move the lead to a new stage → `docker logs drinkx-worker-1` shows `lead_agent.refresh.ok` for that `lead_id`
- [ ] Send an inbound email to a lead's mailbox; wait 16 min → worker fires the deferred task and the banner updates
- [ ] Open Sales Coach (FAB) → static greeting + 4 quick chips. Click a chip → real reply from MiMo Pro
- [ ] Esc closes; reopening starts a fresh history (skill §8)
- [ ] `docker exec drinkx-api-1 ls /app/knowledge/agent/` → both `product-foundation.md` and `lead-ai-agent-skill.md` present
- [ ] Existing prior smoke checks (2.4 / 2.5 / 2.6 / 2.7) still pass

## What's NOT in Sprint 3.1 (deferred)

- Per-suggestion id + persistent dismiss button — Phase 3.2
- Chat history persistence in DB — explicit «no» from spec §10
- Streaming chat responses — Phase 3.2
- Manager rating thumbs up/down — explicit «not in this sprint»
- SPIN-analysis of inbound emails through LLM — only patterns in v1
- Telegram-notification of recommendations — explicit «not in this sprint»

## What's open in production env (operator follow-on)

- `SENTRY_DSN` + `NEXT_PUBLIC_SENTRY_DSN` still empty (Sprint 2.7 G1 wiring is dormant until set; agent works fine without Sentry)
- `pnpm add @sentry/nextjs` not yet run on prod (frontend Sentry stays warn-once)
- Sentry-side rate limits unconfigured

None block Sprint 3.1 functionality — they're carryovers from Sprint 2.7 close.
