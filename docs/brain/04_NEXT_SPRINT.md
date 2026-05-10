# Next Sprint: Phase 3 Sprint 3.1 — Lead AI Agent

Status: **READY TO PLAN** (after Sprint 2.7 PR #12 merge / deploy / smoke)
Branch: `sprint/3.1-lead-ai-agent` (create from main once 2.7 lands)
Authoritative spec: [`docs/SPRINT_3_1_LEAD_AI_AGENT.md`](../SPRINT_3_1_LEAD_AI_AGENT.md)

## Goal

Unified AI agent inside the lead card. Two modes on a single
system prompt:

- **Background** — Celery task watches for paused conversations + sales-
  methodology gaps (SPIN phase missing, no economic buyer, gate
  blockers, rotting deal). Surfaces a banner-recommendation between
  the LeadCard header and the tabs when it has something to say,
  silent otherwise.
- **Foreground** — Sales Coach chat drawer. FAB-button opens a chat
  with full lead context (stage, AI Brief, contacts, last 20
  activities, KB excerpts by segment). Manager asks «что делать
  дальше», gets a contextual reply.

Both modes share `app/lead_agent/prompts.py` which assembles the
system prompt from `docs/knowledge/agent/product-foundation.md`
(always-on) + relevant sections of `docs/skills/lead-ai-agent-skill.md`
+ a serialised `LeadAgentContext`.

## Read before starting

- `docs/SPRINT_3_1_LEAD_AI_AGENT.md` — full sprint spec, top to bottom
- `docs/brain/00_CURRENT_STATE.md` — state after Sprint 2.7 merge
- `docs/brain/01_ARCHITECTURE.md` §5 — AI Modules
- `app/enrichment/` — LLMProvider Protocol pattern (ADR-018) — re-use, do not duplicate
- `app/knowledge/` — KB-file loader pattern (lru_cache, segment matcher) — re-use
- `app/automation/stage_change.py` — Phase E hook site
- `app/inbox/processor.py` — second Phase E hook site (with countdown=900 to give the manager 15 min before the agent fires)

## ⚠️ Phase A is blocked on the user

The spec references two files that don't exist in the repo yet:

- `docs/skills/lead-ai-agent-skill.md` — the agent's behavioural skill (system prompt structure, when to fire what, output format)
- `docs/knowledge/agent/product-foundation.md` — DrinkX product context the agent always reads first

**Phase A copies these from artifacts the user will provide.** The
next session for Sprint 3.1 should ask for them up front and
cite this section. Without them, Phase C can't build a meaningful
system prompt and Phase A can't even start.

## Migration index correction

The spec says **migration 0013** for the new `leads.agent_state`
column. That index has been taken since Sprint 2.3 G1
(`0013_default_pipeline`). Sprint 2.7 G2 added `0021_automation_steps`.
**The actual next free index is 0022.** Update the migration file
header accordingly when Phase B runs.

## Scope

(Tracked in `docs/SPRINT_3_1_LEAD_AI_AGENT.md`. Phase summary below.)

### Phase A — Knowledge files in repo (~15 min)
Copy artifacts into the repo:
- `docs/skills/lead-ai-agent-skill.md`
- `docs/knowledge/agent/product-foundation.md`

Both files are read from disk into a process-cached system prompt
(`_FOUNDATION_CACHE` + `_SKILL_CACHE`), not stored in DB or Redis.

### Phase B — Migration 0022 (~30 min)
ALTER TABLE leads ADD COLUMN agent_state JSONB NOT NULL DEFAULT '{}'.
Pydantic shape:

```python
class AgentState(BaseModel):
    spin_phase: str | None = None          # "Situation" | "Problem" | "Implication" | "Need-payoff"
    spin_notes: str | None = None
    missing_contacts: list[str] = []       # ["economic_buyer", "champion"]
    gate_blockers: list[str] = []
    suggestions_log: list[SuggestionLog] = []
    silence_alert_sent_at: datetime | None = None
    last_analyzed_activity_id: str | None = None
    coach_session_count: int = 0
```

### Phase C — Backend `app/lead_agent/` (~2–3 days)
Package-per-domain (ADR-009). Modules:
- `schemas.py` — AgentState, AgentSuggestion, ChatMessage, ChatRequest
- `context.py` — LeadAgentContext: assembles full context for one lead via existing repos (no new DB queries)
- `prompts.py` — builds system prompt from knowledge files (cached)
- `runner.py` — calls LLM via `get_llm_provider()` fallback chain (Flash for background, Pro for chat)
- `tasks.py` — Celery `lead_agent.background_check(lead_id)` + `scan_silence` (every 6h)
- `routers.py` — 3 endpoints: GET `/leads/{id}/agent-suggestion`, POST `/leads/{id}/agent-chat`, PATCH `/leads/{id}/agent-suggestion/{suggestion_id}/action`

Rate limit: Redis key `agent_notif:{lead_id}` with TTL 24h prevents
the same lead from generating multiple banner-recommendations per
day.

### Phase D — Frontend (~1 day)
- `apps/web/components/lead/AgentBanner.tsx` — between header and tabs; shows when `suggestion.silent === false`; ✕ marks `manager_action='ignored'`; action buttons dispatch by `intent`
- `apps/web/components/lead/SalesCoachDrawer.tsx` — FAB toggle, quick chips («Что делать дальше», «Напиши follow-up», «Разбери возражение», «Проверь готовность к переходу»), in-memory chat history (no DB persist in v1)

### Phase E — Existing-code hooks (~2–3 hours)
Two minimal hooks:
1. `app/automation/stage_change.py` — at end of successful transition: `lead_agent_background_check.apply_async(args=[str(lead.id)])`
2. `app/inbox/processor.py` — after new inbound email attached: `lead_agent_background_check.apply_async(args=[str(lead.id)], countdown=900)` (15 min delay so the manager has a chance to react before the agent fires)

## NOT in this sprint

- Streaming chat responses (Phase 3.2)
- Persist chat history in DB
- Manager rating of recommendations (thumbs up/down)
- SPIN-analysis of inbound emails via LLM (pattern-match only for v1)
- Telegram-notification of recommendations

## Risks

| Risk | Probability | Mitigation |
|---|---|---|
| LLM returns invalid JSON | Medium | Fallback to `silent=True`, never crash the parent flow |
| Celery task storm with 200+ active leads | Low | Redis rate-limit key + 24h TTL skip |
| Large context → expensive LLM call | Medium | Cap activities at 20, KB excerpts at 3 segment-matched blocks |
| stage_changed hook blocks transition | Low | Use `.apply_async()` (fire-and-forget), never sync |
| Migration index conflict (spec says 0013) | Resolved | Use 0022 instead — see «Migration index correction» above |
| Phase A artifacts not provided | High | Ask user up front; don't start coding without the skill + foundation files |

## Stop conditions — post-deploy smoke checklist

Update `docs/SMOKE_CHECKLIST_3_1.md` with:
- [ ] Open a lead card with last activity > 3 days ago
- [ ] Manually trigger: `celery call lead_agent.background_check --args='["<lead_id>"]'`
- [ ] Reload card → banner appears with title + body + 1–2 action buttons
- [ ] Click action → `intent` dispatches correctly (composer / coach / gate)
- [ ] Open Sales Coach → ask «что делать дальше» → response cites stage + AI Brief + recent activities
- [ ] Close Sales Coach → `coach_session_count` incremented in `lead.agent_state`
- [ ] Existing 9 prior 2.7 + 8 prior 2.6 + 7 prior 2.5 + 9 prior 2.4 smoke checks still pass

## Done definition

- Migration 0022 (`leads.agent_state`) applies cleanly via `alembic upgrade head` on staging
- Background `lead_agent.background_check` Celery task fires for new inbound emails (15 min delay) and stage transitions (immediate); rate-limit key prevents duplicate banners within 24h
- LeadCard banner renders + dismisses + action buttons fire
- Sales Coach drawer end-to-end: open → first-message greeting → manager turn → contextual reply citing AI Brief + stage
- ≥10 mock tests for prompt assembly, runner JSON parsing, scan_silence query shape, banner state transitions
- `pnpm typecheck` + `pnpm build` clean
- Sprint report written, brain memory rotated

---

**Out-of-scope but parked here for awareness — fold into 3.2+:**

(Inherited from Sprint 2.7 G3 + G4 deferral, now Sprint 2.8+ territory; reproduced here so the Sprint 3.1 session knows what's in the long-tail.)

- tg channel outbound dispatch — Telegram Bot API client + `lead.tg_chat_id` migration + LeadCard input + `send_telegram` tri-state contract
- Enrichment → Celery + WebSocket — `_bg_run` migration to `app.scheduled.jobs.enrichment_run`; `/ws/{user_id}` WebSocket; real-time progress on `/leads/{id}` AI Brief tab
- SMS provider evaluation
- Multi-tenancy (Phase 3.X+)
- Workspace-level webhook trigger / action
- AI-generated message bodies in templates
- AmoCRM adapter
- Telegram Business inbox + `gmail.send` scope
- Quote / КП builder
- Knowledge Base CRUD UI
- `_GENERIC_DOMAINS` per-workspace setting
- Gmail history-sync resumable / paginated job
- Honeypot / timing trap on `embed.js`
- Per-stage gate-criteria editor
- Pipeline cloning / templates marketplace
- Cross-pipeline reporting
- DST-aware cron edge handling
- Stage-replacement preview in PipelineEditor
- Workspace AI override → fallback chain wiring
- Multi-clause condition UI in the Automation Builder modal
- Default pipeline 6–7 stages confirm
- Custom-field boolean kind + autosave retry + keyboard nav
- Auto-discover `lead.tg_chat_id` from Gmail inbox
- Multi-step automation polish: dnd-kit reorder, pause-mid-chain UI, per-step retry on failure
