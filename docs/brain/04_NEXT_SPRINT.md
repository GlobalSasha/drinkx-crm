# Next Sprint: Phase 3 Sprint 3.2 — Lead AI Agent polish

Status: **READY TO PLAN** (Sprint 3.1 closed and deployed 2026-05-10)
Branch: `sprint/3.2-lead-agent-polish` (cut from main after this brain rotation lands)
Authoritative report from 3.1: [`docs/SPRINT_3_1_LEAD_AI_AGENT_REPORT.md`](../SPRINT_3_1_LEAD_AI_AGENT_REPORT.md)

## Goal

Close the gap between the agent skill spec and what shipped in v1.
Sprint 3.1 deliberately parked five items as out-of-scope to keep
the surface small; 3.2 picks them up once managers have actually
used the banner + chat in production.

## Read before starting

- `docs/SPRINT_3_1_LEAD_AI_AGENT_REPORT.md` — closure report from 3.1
- `apps/api/knowledge/agent/lead-ai-agent-skill.md` — agent behaviour, especially §11 «Special scenarios» (the «менеджер игнорирует советы» branch is documented but unwired)
- `apps/api/app/lead_agent/runner.py` — current `get_suggestion` + `chat` shapes
- `apps/api/app/lead_agent/schemas.py` — current `AgentSuggestion` shape (no `id` yet)
- `apps/web/components/lead-card/AgentBanner.tsx` — current dismiss is session-only
- `apps/web/components/lead-card/SalesCoachDrawer.tsx` — current chat is sync POST

## Scope

### Allowed (5 features)

#### G1 — Per-suggestion id + persistent dismiss (~0.5 day)
- Backend: `runner.get_suggestion` generates `suggestion.id = uuid4()`. Stored verbatim in `agent_state['suggestion']['id']`.
- New `agent_state['dismissed_suggestion_ids']: list[str]` (cap at 50, FIFO eviction). When the GET endpoint sees `suggestion.id in dismissed_suggestion_ids`, it returns `{"suggestion": null}` (banner stays hidden).
- Frontend: dismiss button POSTs to a new `/leads/{id}/agent/suggestion/dismiss` endpoint with `{suggestion_id}`. Optimistically hides the banner client-side.
- No DB migration — `agent_state` is opaque JSONB.

#### G2 — Manager rating + adaptive tone (~1 day)
- Backend: new endpoint `POST /leads/{id}/agent/suggestion/rate` with `{suggestion_id, vote: "up" | "down"}`. Appends to `agent_state['suggestions_log']` (already documented in the skill).
- Runner adapts: when the last 3 logged suggestions for the lead have `rating == "down"`, prepend a one-line tone-softening directive to the system prompt («Этот менеджер часто отказывается от рекомендаций — будь короче и менее настойчив»).
- Frontend: thumbs up / thumbs down buttons in the banner footer next to the confidence badge.

#### G3 — SPIN-analysis of inbound emails through LLM (~1 day)
- The current pattern-match heuristic in `runner.get_suggestion` only catches obvious silence + stage gaps. For new inbound emails (the Phase E `countdown=900` path), the agent should LLM-analyse the email body to extract: did the client name an objection? a new stakeholder? urgency?
- New helper `_analyse_inbound(email_body)` in `runner.py` — focused second Flash call returning `{objection: str, urgency: str, new_stakeholder: str}`. Mirrors `_extract_contacts_from_sources` in enrichment for shape.
- The result goes into `agent_state['inbound_signals'][activity_id]` so subsequent suggestion runs can read it without re-hitting the LLM.

#### G4 — Chat streaming via SSE (~1.5 days)
- Replace the sync POST in `routers.py:lead_chat` with SSE response (`StreamingResponse` + `text/event-stream`).
- Update `runner.chat` to yield tokens as they arrive from MiMo Pro (the OpenAI-compatible API supports `stream=true`).
- Frontend: replace the current `useMutation` with an `EventSource` reader; append tokens to the in-progress assistant message.
- WebSocket alternative deferred — SSE is simpler and runs through nginx without extra config.

#### G5 — Sprint close (~0.5 day)
- Sprint report `docs/SPRINT_3_2_LEAD_AGENT_POLISH_REPORT.md`
- Brain rotation (00 + 02 + 04)
- Smoke checklist additions

### Out of scope (parked for Sprint 3.3+)

- **Telegram-notification of recommendations** — pairs naturally with Sprint 2.8 G3 carryover (tg outbound dispatch). Move when 2.8 is in scope.
- **Multi-agent coordination** (per-channel agents) — premature; v1 single agent is enough until customer feedback says otherwise.
- **Voice input for chat** — Phase 4 territory.
- **Batch suggestions** — show «top 10 leads needing attention» on `/today`. Would need a new `/me/agent-priorities` endpoint and is more reporting than agent work; defer.

### Carryovers from Sprint 2.7 + 2.8 still parked

These haven't moved — `docs/brain/02_ROADMAP.md` Sprint 2.8 long-tail covers them:

- tg channel outbound dispatch (Sprint 2.7 G3 deferral)
- Enrichment → Celery + WebSocket (Sprint 2.7 G4 deferral)
- Multi-step automation polish (dnd-kit reorder, pause-mid-chain UI, per-step retry)
- AmoCRM adapter
- Telegram Business inbox + `gmail.send` scope
- Quote / КП builder
- Knowledge Base CRUD UI
- Multi-clause condition UI in Automation Builder
- Sentry DSNs activation (operator step open since 2.7 G1)
- `pnpm add @sentry/nextjs` on prod (operator step)

## Risks

| Risk | Probability | Mitigation |
|---|---|---|
| `agent_state` JSON grows unboundedly | Medium | G1 caps `dismissed_suggestion_ids` at 50 with FIFO eviction; G2 caps `suggestions_log` at 100 |
| LLM streaming on MiMo Pro is unreliable | Medium | Fall back to non-streaming response if first chunk doesn't arrive within 3s |
| Adaptive tone (G2) feels jarring to managers | Low | Single-line directive that's easy to roll back; instrument with structlog so we can audit when it triggers |
| Per-suggestion id breaks existing rows | Low | Migration not needed; old rows without `id` get a new id on next refresh |

## Done definition

- All 5 G items shipped + tested + deployed
- Per-suggestion dismiss survives page reload
- Adaptive tone fires after 3 down-votes in a row (verifiable from worker logs)
- New inbound emails populate `agent_state['inbound_signals']` within 15 min of arrival
- Chat responses stream token-by-token instead of arriving all at once
- Sprint report written, brain rotation complete

## Active migrations on `main` after Sprint 3.1

`0001..0022` — Sprint 3.1 G2 added `0022_lead_agent_state`. Sprint 3.2 should NOT need a new migration — `agent_state` is opaque JSONB. If a 3.2 feature does need one, the next free index is `0023`.

## Stop conditions — post-deploy smoke checklist

Update `docs/SMOKE_CHECKLIST_3_2.md` with:
- [ ] Dismiss a suggestion → reload page → banner stays hidden
- [ ] Force refresh from worker → new suggestion appears with new `id`, banner re-shows
- [ ] Rate a suggestion thumbs-down 3× in a row on the same lead → next suggestion's prompt has the softening directive (verifiable by inspecting worker structlog at `lead_agent.suggestion.adaptive_tone`)
- [ ] Send an inbound email mentioning a new objection → 15 min later, `agent_state['inbound_signals']` populated for that activity
- [ ] Open Sales Coach → ask a long-form question → tokens stream in incrementally rather than arriving all at once
- [ ] Existing 3.1 + 2.7 smoke checks still pass
