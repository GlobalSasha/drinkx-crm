# DrinkX CRM — Key Decisions (ADRs)

| ID | Title | Status |
|---|---|---|
| ADR-001 | Today-first IA | ✅ |
| ADR-002 | 11-stage pipeline (not 5-6) | ✅ |
| ADR-003 | Gate criteria per stage transition | ✅ |
| ADR-004 | Two scoring systems, never conflate | ✅ |
| ADR-005 | Deal Type = required field, 6 values | ✅ |
| ADR-006 | Priority A/B/C/D (replaces tier 1/2/3 numeric) | ✅ |
| ADR-007 | AI proposes, human approves — always | ✅ |
| ADR-008 | DeepSeek V3 primary, GPT-4o for vision/high-value | ⚠ superseded by ADR-018 |
| ADR-009 | Package-per-domain backend (not layered) | ✅ |
| ADR-010 | Rotting = two independent rules | ✅ |
| ADR-011 | Pilot Success Contract activates at Stage 9 | ✅ |
| ADR-012 | Economic Buyer required from Stage 6 | ✅ |
| ADR-013 | Bare-metal hosting (not Vercel/Railway) | ✅ |
| ADR-014 | Stub-mode auth before Supabase keys | ✅ |
| ADR-015 | Lead Pool + Weekly Sprint System (PRD-addition v2.1) | ✅ |
| ADR-016 | B2B model (index-b2b.html) is official target; PRD v2.0 outdated | ✅ |
| ADR-017 | Scoring criteria = separate table `scoring_criteria`, per-workspace | ✅ |
| ADR-018 | MiMo (Xiaomi) is primary LLM; chain MiMo → Anthropic → Gemini → DeepSeek | ✅ |
| ADR-019 | Email ownership model — lead-scoped, not manager-scoped | ✅ |
| ADR-020 | Widen `alembic_version.version_num` to VARCHAR(255) before each migration | ✅ |
| ADR-022 | Company = Account; Lead = Deal/Opportunity. `leads.company_name` is a snapshot, not source of truth | ✅ |
| ADR-023 | Score 0–100 is manager-manual, not AI. Backend recomputes total + priority from `leads.score_details_json` on every PATCH | ✅ |
| ADR-024 | Unified Activity Feed — Чак is a feed participant, drawer/banner removed | ✅ |
| ADR-025 | `lead_stage_history` is a dedicated table, not derived from `activities.stage_change` payload | ✅ |
| ADR-026 | `leads.primary_contact_id` is a separate concept from `contacts.role_type` — pinning, not role | ✅ |

---

## ADR-001 Today-first IA
Main screen = Daily Plan (not Pipeline). Manager opens CRM → sees "do this,
in this order". Pipeline is secondary map view.

## ADR-002 11-stage pipeline (not 5-6 stage)
Full B2B enterprise cycle: Discovery → Solution Fit → Business Case →
Multi-stakeholder → Договор → Производство → Pilot → Scale.
Previous 5-stage was too coarse for enterprise sales management.

## ADR-003 Gate criteria per stage transition
Modal checklist on stage move (not free drag). Without gates, pipeline is
decorative — managers move cards without progress.
Implementation: `stage.gate_criteria_json` field, displayed in modal, stored
as event in `activities` on transition.

## ADR-004 Two scoring systems, never conflate them
- `fit_score` (0–10): **AI auto**, computed by Research Agent, ICP match
- `Score` (0–100): **manager manual**, 8 criteria with weights
- Tier A/B/C/D derived from Score, NOT from fit_score

Both stored separately in Lead model. UI shows them side-by-side in scoring tab.

## ADR-005 Deal Type = required field, 6 values
Enterprise Direct / QSR / Distributor-Partner / Raw materials partner /
Private small / Service repeat. Enables pipeline filtering and partner-track
routing through Assignment Engine.

## ADR-006 Priority A/B/C/D (replaces tier labels)
A = Strategic Tier 1 (Score 80+, личное управление)
B = Promising Tier 2 (60-79, активная работа)
C = Low Tier 3 (40-59, nurture)
D = Archive (<40, автообработка)
Assigned at Stage 2 as gate condition.

## ADR-007 AI proposes, human approves — always
No automated outbound messages without explicit manager approval.
No auto-actions in B2B context — one wrong message kills a deal.
Even auto_email reminders are drafts requiring manager click-to-send.

## ADR-008 DeepSeek V3 primary, GPT-4o for vision + high-value only ⚠ SUPERSEDED
**Superseded by ADR-018 (2026-05-06). DeepSeek is now a fallback, not the primary.**

Original reasoning kept for history:
> Cost: DeepSeek ~$0.0003/1K tokens vs GPT-4o ~$0.01/1K (33× cheaper).
> GPT-4o reserved for: visit-card OCR (vision), fit≥8 re-enrichment (premium).
> Gemini 1.5 Pro as fallback if both fail.

## ADR-009 Package-per-domain backend (Krayin pattern)
NOT layered (controllers/services/repos at top level) but domain packages
each containing their own models/schemas/repositories/services/tasks/routers/events.
Rationale: prevents cross-domain coupling, easier to add/remove features,
mirrors how the product is described in PRD §6.

## ADR-010 Rotting = two independent rules
- **Rule 1 (stage-rot):** time in stage > stage.rot_days → flag
- **Rule 2 (next-step-rot):** next_action_at empty or overdue
  - 3 days = yellow warning
  - 7 days = red danger
Both run independently in Celery. Both visible in Today + Kanban.
Stored as boolean flags on Lead, recomputed by `rotting_evaluator` cron.

## ADR-011 Pilot Success Contract activates at Stage 9
Separate tab in lead card, conditionally rendered when `lead.stage.position >= 9`.
Fields: pilot goal, period, locations, 6 success metrics
(cups/day, uptime, avg check, service time, incidents/month, baseline),
responsible parties, review date, post-pilot decision.
Stored as `lead.pilot_contract_json` (embedded, no separate table for now).

## ADR-012 Economic Buyer required from Stage 6
Gate Stage 7 blocks if no contact with `role_type = economic_buyer`.
Warning shown in contacts tab and sidebar gate checklist.
Hard-coded gate rule (not configurable per workspace) because it's a B2B
sales discipline principle, not a per-customer choice.

## ADR-013 Bare-metal hosting (not Vercel/Railway)
User provided own Ubuntu 22.04 server (77.105.168.227 / crm.drinkx.tech).
Stack runs as Docker Compose: postgres + redis + api + web bound to
`127.0.0.1`, exposed via host nginx with Let's Encrypt TLS.
Auto-deploy via GitHub Actions SSH workflow (deploy.sh).
PRD §8.5 originally specified Vercel + Railway + Supabase managed —
all those still **valid migration targets**, but bare-metal is current state.

## ADR-014 Stub-mode auth before Supabase keys
`SUPABASE_JWT_SECRET=""` triggers stub identity (`dev@drinkx.tech`).
All endpoints work end-to-end without external auth provider.
Switches to real Google OAuth verification when secret is set — zero code change.
Allows full backend development before Supabase project is created.

## ADR-016 B2B model (index-b2b.html) is the official target

`crm-prototype/index-b2b.html` supersedes PRD v2.0 on the following points.
Work from brain files (`00_CURRENT_STATE.md`, `04_NEXT_SPRINT.md`) — NOT from PRD v2.0 — for:
- Pipeline stages (6-stage → 11-stage B2B cycle)
- Priority A/B/C/D (replaces tier labels 1/2/3)
- Deal Type field (required, 6 enum values)
- Scoring 0–100 with 8 weighted criteria
- Multi-stakeholder contact roles (Economic Buyer / Champion / Technical / Operational)
- Pilot Success Contract (Stage 9+)

PRD v2.0 remains authoritative for everything else (IA, enrichment, daily plan, phase/billing structure).

## ADR-017 Scoring criteria = separate table, per-workspace

Scoring config is NOT a JSON blob on `workspaces` — it lives in a dedicated table.

```sql
scoring_criteria (
  id          UUID PK,
  workspace_id UUID FK → workspaces.id CASCADE,
  criterion_key  VARCHAR(60) NOT NULL,   -- e.g. "scale_potential"
  label          VARCHAR(120) NOT NULL,  -- display name
  weight         INTEGER NOT NULL,       -- points out of 100 (all sum to 100)
  max_value      INTEGER NOT NULL DEFAULT 5  -- slider max (1-5 by default)
)
```

Default seed (8 criteria from index-b2b.html) applied in workspace bootstrap:
| key | label | weight |
|---|---|---|
| scale_potential | Масштаб потенциала | 20 |
| pilot_probability_90d | Вероятность пилота 90д | 15 |
| economic_buyer | Экономический покупатель | 15 |
| reference_value | Референсная ценность | 15 |
| standard_product | Стандартный продукт | 10 |
| data_readiness | Готовность данных | 10 |
| partner_potential | Партнёрский потенциал | 10 |
| budget_confirmed | Бюджет подтверждён | 5 |

Rationale: JSON config can't be typed, queried, or validated. Separate table allows
per-workspace label customisation, future audit trail of weight changes, and typed API responses.

## ADR-015 Lead Pool + Weekly Sprint System
(per PRD-addition v2.1 in prototype repo)
Leads live in shared **pool**, managers don't own base.
"Сформировать план на неделю" → take N=20 cards (workspace.sprint_capacity_per_week)
filtered by city + segment, pseudo-random within priority.
Race-safe via optimistic UPDATE-WHERE-pool.
Transfer between managers logged as activity.
Implemented in Sprint 1.2.

## ADR-018 MiMo (Xiaomi) as primary LLM; multi-provider fallback chain

**Date:** 2026-05-06
**Supersedes:** ADR-008 (DeepSeek-primary)

### Decision

Primary LLM provider is **Xiaomi MiMo V2** via the OpenAI-compatible endpoint
`https://api.xiaomimimo.com/v1`. Two SKUs are used:

- `mimo-v2-flash` — bulk / cheap. Default for: Research Agent synthesis, Daily Plan
  generation, Quality pre-filter (regex + mini-LLM go/no-go).
- `mimo-v2-pro` — heavy reasoning. Default for: high-fit (≥8) re-enrichment,
  Sales Coach chat, scoring assistance, anything the user judges high-stakes.

Fallback chain on 5xx / rate-limit / auth-error:
**MiMo → Anthropic (`claude-sonnet-4-5`) → Gemini → DeepSeek**.

OpenAI GPT-4o is reserved for vision (visit-card OCR) and emergency only —
it is not part of the text fallback chain.

### Why not DeepSeek-primary (ADR-008)

- MiMo Flash matches DeepSeek's price tier with stronger long-context support
  (1M token context on Pro vs DeepSeek's 64K) — useful for Knowledge-Base-grounded
  synthesis where the lead profile + KB excerpts + tool outputs can be large.
- Anthropic as the first fallback gives a true quality ceiling for reasoning-heavy
  tasks if MiMo degrades; DeepSeek (now last in chain) only fires when both MiMo
  and Anthropic fail.
- Single-vendor primary risk: keeping Anthropic, Gemini, DeepSeek wired means we
  can swap primary in one env-var flip if MiMo pricing or availability shifts.

### Implementation rule

Sprint 1.3 lands `app/enrichment/providers/{mimo,anthropic,gemini,deepseek,openai}.py`,
each implementing a common `LLMProvider` Protocol. The factory
`get_llm_provider(task_type)` reads `CRM_AI_BACKEND` (default `"mimo"`) and
`LLM_FALLBACK_CHAIN` (default `["mimo","anthropic","gemini","deepseek"]`)
from env, walking the chain on failure.

`task_type` switches the model SKU within MiMo:
- `task_type in ("research_synthesis","daily_plan","prefilter")` → `MIMO_MODEL_FLASH`
- `task_type in ("sales_coach","scoring","reenrichment_high_fit")` → `MIMO_MODEL_PRO`

### Env contract

```
MIMO_API_KEY=
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
MIMO_MODEL_PRO=mimo-v2-pro
MIMO_MODEL_FLASH=mimo-v2-flash
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
OPENAI_API_KEY=          # vision only
CRM_AI_BACKEND=mimo
LLM_FALLBACK_CHAIN=["mimo","anthropic","gemini","deepseek"]
```

### Scope of this ADR

This ADR only changes config defaults and documentation. Runtime provider code
will be implemented in Sprint 1.3 along with the Research Agent.

## ADR-019 Email ownership model — lead-scoped, not manager-scoped

Date: 2026-05-08
Status: ✅

Decision: Emails belong to the lead card, not to the manager whose Gmail
account sourced them.

- `Activity.user_id` = audit trail (which manager's Gmail sent/received it).
- NOT a visibility filter — all team members see all emails on a lead.
- Rationale: B2B context is a company asset; transfers don't lose history;
  AI Brief benefits from full correspondence signal regardless of who wrote it.

Implementation:
- `Activity.lead_id` is the only required scope key for the lead-card feed.
- `Activity.user_id` is set to the channel's owner when the channel is
  user-scoped, NULL when the channel is workspace-scoped.
- Activity Feed queries (Lead Card → Activity tab, AI Brief context
  injection) filter strictly by `lead_id + workspace_id`, never by user.
- Notifications stay per-user (Sprint 1.5) — independent of the underlying
  activity row.

Implemented in Sprint 2.0 (Groups 3–6).

## ADR-020 Widen `alembic_version.version_num` to VARCHAR(255) before each migration

Date: 2026-05-09
Status: ✅

Decision: Every new migration's `upgrade()` starts with

```python
op.execute(
    "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
)
```

before any other DDL.

Context: Alembic's bookkeeping table `alembic_version` defaults to
`version_num VARCHAR(32)`. Several of our recent revision IDs
(`0009_inbox_items_and_activity_email` is 38 chars, similar names will
keep coming) overflow that and crash the upgrade with a Postgres
`value too long for type character varying(32)` error. Widening to
255 once would be enough — but we're not always sure which version of
the column is in front of us (fresh deploy vs. legacy snapshot vs.
restored backup), so we re-issue the `ALTER TABLE` defensively at the
start of every migration. `ALTER … TYPE VARCHAR(255)` on an
already-VARCHAR(255) column is a no-op in Postgres and costs nothing.

Implementation:

- Each new migration starting with `0012_*` opens its `upgrade()` with
  the line above. Older migrations (`0001_*` … `0011_*`) are not
  retro-edited — those revision IDs are short enough to fit.
- Idempotent on production: `ALTER COLUMN ... TYPE VARCHAR(255)` is a
  no-op when the column is already that wide.
- We don't issue a corresponding shrink in `downgrade()` — once widened,
  the column stays wide. Shrinking back to 32 would just bring the
  problem back.

Why not handle this once in `alembic/env.py`?

We considered a one-shot widening hook in `env.py` that runs before
the migration list. Two reasons we didn't:

1. `env.py` runs the same on every alembic invocation, including the
   `--sql` offline mode that generates SQL for review without touching
   the DB. Putting DDL there would emit phantom `ALTER TABLE` lines into
   every offline diff.
2. New developers running migrations against a freshly-cloned dev DB
   benefit from the per-migration safety net — one place to look,
   right next to the schema change being applied.

Per-migration explicit-ness > implicit env hook for a 1-line snippet.

## ADR-021 Single-workspace model — bootstrap joins existing

DrinkX is a single-team product. Until 2026-05-08 the auth bootstrap
created a brand-new Workspace for every first-time signing user, so
two team members signing in produced two disconnected silos —
different lead pools, different pipelines, different notifications,
different audit trails. Two such silos accumulated in production
(«Gmail» 1fa8ccb3-…, «Drinkx» 456610a9-…) before the issue was
caught — the first user to sign in with a personal Google account
landed in workspace A; signing in later with the work email created
workspace B with zero leads.

**Decision:** the auth bootstrap is single-workspace. The first ever
user signing in CREATES the workspace + bootstrap pipeline; every
subsequent user JOINS the existing canonical workspace
(`SELECT * FROM workspaces ORDER BY created_at ASC LIMIT 1`) as
`role='manager'`. No invites, no manual workspace assignment.
Per-user isolation is already handled at the lead level via
`assignment_status='assigned'` + `assigned_to=user_id` (ADR-015 Lead
Pool + Weekly Sprint System).

The workspace name comes from the `WORKSPACE_NAME` env var (default
"DrinkX") instead of being derived from the first signup's email
domain — config, not data accident.

**Trade-off:** if DrinkX ever sells the same CRM codebase to a
second brand, this single-workspace assumption breaks. That's a
Phase 3 «multi-tenancy» problem (invite-flow + domain-based routing
or per-tenant DBs); v1 stays simple.

Implementation:

- `app/auth/services.py:upsert_user_from_token` — first-user path
  creates workspace + bootstrap pipeline + sets default_pipeline_id;
  subsequent-user path SELECTs the oldest workspace and creates the
  user with role=manager pointed at it.
- `app/config.py:Settings.workspace_name` — `"DrinkX"` default,
  override via env var.
- Migration `0015_merge_workspaces` — one-time data migration that
  folded the two existing production workspaces into one (leads
  remapped by stage NAME — both workspaces seeded from
  DEFAULT_STAGES so name-match is reliable). Idempotent: short-
  circuits on databases that don't have the source UUID.
- `tests/test_auth_bootstrap.py` — 3 mock-only tests
  (first_user_creates / second_user_joins / existing_user).

What this does NOT do:
- No multi-tenancy. Adding a second tenant is a Phase 3 design
  decision; the current code would silently put their users into
  the original workspace.
- No invite flow. v1 trusts that anyone able to OAuth-sign-in is a
  team member. Tightening this (domain allow-list, explicit invite
  table) is a Sprint 2.4+ surface (the `Команда` section of
  /settings).
- No automatic role promotion. Subsequent users always land as
  manager; only the first-ever user is admin. The admin can
  promote others manually via `/settings → Команда` once that lands
  in Sprint 2.4 G1.

## ADR-022 Company = Account, Lead = Deal/Opportunity

**Decision.** Adopt the standard B2B CRM account-layer model:
`companies` is the stable identity (name, INN, domain, contacts);
`leads` is the working state (stage, segment, score, owner). One
company can have many leads; closing a lead doesn't touch the
company.

**`leads.company_name` is a snapshot/cache, not source of truth.**
Renames flow one direction: PATCH /companies/{id} → propagate to
`leads.company_name` for ACTIVE leads only (closed/won/lost and
archived leads keep their historical snapshot). Direct edit of
`leads.company_name` via PATCH /leads/{id} is REJECTED with 409
`company_name_locked` when `lead.company_id IS NOT NULL`.

**Dedup is by `normalized_name`,** computed in
`app/companies/utils.py:normalize_company_name`: lowercase + strip
quotes + strip RU/EN org-forms (ООО / ПАО / LLC / GmbH / …) +
collapse whitespace. `normalized_name` is never accepted from the
frontend.

**Creation = duplicate-warning protocol.** POST /api/companies
returns 409 with `error: "duplicate_warning"` + candidates list
(including `leads_count`) when an active company has the same
`normalized_name`. Client may retry with `?force=true` after the
manager confirms.

**Merge.** POST /api/companies/{source}/merge-into/{target}:
- 409 `inn_conflict` when source.inn != target.inn (override with
  `?force=true`).
- Active non-terminal leads inherit `target.name`; closed/won/lost
  and archived leads keep their snapshot. (The spec said
  `is_archived = false`; the actual lead column is `archived_at` —
  implementation uses `archived_at IS NULL`.)
- Contacts re-point at `target`.
- Source archived, audit `company.merge` row written.

**Backlog (Phase 2):**
- `lead_contacts` junction table (today: one-to-many via
  `contacts.lead_id` only).
- `company_aliases` table.
- Company-level AI Brief.
- Company-level tasks (separate from lead activities).

**Migration index.** 0023_companies + 0024_contacts_workspace_id_not_null.
Operator runs `scripts/backfill_companies.py --apply` between the
two — the second migration's defensive check refuses to run when
any `contacts.workspace_id IS NULL`.

**pg_trgm.** Sprint 3.3 turns on `CREATE EXTENSION IF NOT EXISTS pg_trgm`
so `app/search/` can use `similarity()` + the `%` operator on
companies/leads/contacts name columns. Short queries (len < 3)
fork into `_search_ilike` to avoid noise.


## ADR-023 Score 0–100 is manager-manual, not AI

**Date:** 2026-05-16
**Status:** ✅ (Sprint Lead Card v2, PR [#45](https://github.com/GlobalSasha/crm/pull/45))

**Decision.** The 8-criteria Score 0–100 is filled in by the manager
through an editable popup (`ScoreBreakdownModal`). The AI Research
Agent does NOT write to `leads.score`, `leads.priority`, or
`leads.score_details_json`. The two scoring systems from ADR-004
stay split:

- `fit_score` (0–10): AI auto, written by the orchestrator, **kept in
  DB for future surfaces but not shown on the LeadCard.**
- `Score` (0–100): manager manual, 8 criteria with weights, persisted
  to `leads.score_details_json`. Server recomputes `leads.score`
  + `leads.priority` (A/B/C/D via 80/60/40 thresholds, see ADR-006)
  on every `PATCH /leads/{id}/score-details`. Priority is derived
  state, never set independently by the client.

**Why not let AI do it.** The 8 criteria (Масштаб потенциала,
Вероятность пилота 90д, Экономический покупатель, …) are sales
judgements grounded in conversations the AI doesn't see. Letting the
AI guess at them produced silently wrong priorities and the manager
stopped trusting the score. Manual entry is slower but the number
becomes operationally meaningful.

**Storage shape.**

```
leads.score_details_json = { criterion_key: int 0..max_value, ... }
```

Keys match `scoring_criteria.criterion_key` for the workspace
(per-workspace customisable, see ADR-017). Unknown keys are dropped
silently on PATCH so a workspace-config drift doesn't error out the
write. Out-of-range values raise 400.

**Recompute formula** (mirrored in `app/leads/scoring.py:compute_total`):

```
total = round(Σ (value / max_value) × weight)  for each criterion
priority = A if total ≥ 80 else B if ≥ 60 else C if ≥ 40 else D
```

`priority_label` is a derived Russian word (Стратегический /
Перспективный / Низкий / Архив) computed by
`app/leads/scoring.priority_label` and exposed on `LeadOut` so the
frontend never has to translate the raw letter.

**What if AI scoring comes back later.** Either add a separate
column (`leads.ai_score`, `leads.ai_priority`) or surface
`fit_score` more loudly — don't bolt AI onto the manual column.
Keeping the manual path simple and trustworthy was the whole point.

## ADR-024 Unified Activity Feed — Чак as a feed participant

**Date:** 2026-05-15
**Status:** ✅ (Sprint Unified Activity Feed, PR [#42](https://github.com/GlobalSasha/crm/pull/42))

**Decision.** The LeadCard «Активность» tab is now a single
chronological feed across `activities` rows. The AI assistant Чак
posts to it as a participant — runner suggestions land as
`Activity(type='ai_suggestion')` rows, chat answers come from
`POST /leads/{id}/feed/ask-chak`. The separate `AgentBanner`,
`SalesCoachDrawer`, FAB `🤖 Чак`, and the «Переписка» tab are
DELETED.

**Why.** Three signals from the v1 layout:

1. The banner / drawer / FAB / Переписка tab carved up information
   that managers actually read in time order. Switching back and
   forth was the most-clicked complaint.
2. AI recommendations only made sense in context (last email, last
   stage move, last task). Hiding them in a drawer broke that
   context.
3. The drawer's in-memory chat history vanished on close; managers
   couldn't show a teammate what Чак said yesterday.

**Architecture rules.**

- Feed = `activities` table only. Telegram + phone messages live in
  `inbox_messages` and stay OUT of the feed until those channels are
  productionised (see roadmap «Sprint 3.5»). The «Переписка» tab is
  not coming back; channels will mix INTO the unified feed when
  ready.
- `author_name` is resolved server-side via LEFT JOIN on `users`
  (one round-trip, no N+1) so the feed renders «Менеджер Иван»
  without N+1.
- AI rows override `author_name="Чак"` regardless of the row's
  `user_id` — some chat rows stamp the asking manager for audit;
  the visible author is still Чак.
- `lead_agent_refresh_suggestion` dedupes Activity writes on text —
  silence-scan / stage-change / inbox-attach triggers don't spam
  the feed with the same recommendation.
- `Activity.type` is `String(30)` not Postgres ENUM, so adding
  `ai_suggestion`, `lead_assigned`, `enrichment_done`, `phone`
  needed no migration.

**Composer routing.** Comments starting with `@Чак ...` route to
`/feed/ask-chak`; everything else creates an `Activity` via the
existing `POST /leads/{id}/activities`. Same composer, two backends.

**Trade-off.** A drawer-style chat allowed long back-and-forth
without the answers leaving a permanent feed trail. The new model
makes every Q&A a persistent record — which is what we wanted for
shared workspace context, but means «brainstorming» questions now
clutter the feed. If that bites, add a `payload_json.scratchpad=true`
flag and filter those out of the default feed view.

## ADR-025 `lead_stage_history` is a dedicated table

**Date:** 2026-05-15
**Status:** ✅ (Sprint Lead Card Redesign, PR [#41](https://github.com/GlobalSasha/crm/pull/41))

**Decision.** Stage-transition history lives in its own table
`lead_stage_history` (one open row per lead at any time), not derived
from the existing `activities WHERE type='stage_change'` payload.

```
lead_stage_history (
  id            UUID PK DEFAULT gen_random_uuid(),
  lead_id       UUID NOT NULL FK → leads.id CASCADE,
  stage_id      UUID NOT NULL FK → stages.id CASCADE,
  entered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  exited_at     TIMESTAMPTZ,
  duration_sec  INTEGER
)
INDEX (lead_id, entered_at)
```

**Write path.** `app/automation/stage_change.move_stage` runs a
POST_ACTION `record_stage_history` after applying the new stage:
closes the open row (`exited_at = now()`, `duration_sec =
floor(now - entered_at)`), inserts a fresh open row for the
destination. Wrapped in try/except — a history-write failure never
rolls back the move itself; the `activities.stage_change` row is
still the canonical audit trail.

**Why a separate table, not just consume `activities.payload_json`.**

1. `activities.payload_json` is JSON (not JSONB on the column-type
   level — see ADR around the feed sort-key fix), and querying
   per-stage durations means JSON extract + parse + window function
   per row. With `lead_stage_history`, the dwell-time question
   («how long has this lead been in stage X») becomes
   `SELECT entered_at FROM lead_stage_history WHERE lead_id=? AND
   exited_at IS NULL` — index hit, microseconds.
2. We want workspace-wide analytics (average dwell, leads stuck
   > 14 days) without touching the per-event log. Putting durations
   in `activities` JSON would force every aggregation to do JSON
   extraction at read time.
3. The duration is computed at write time, so historical rows have
   stable values even if `created_at` math drifts (timezone changes,
   etc.).

**Backfill.** `scripts/backfill_stage_history.sql` ran once after
the migration applied: one open row per active lead at
`COALESCE(assigned_at, created_at)` pinned to `leads.stage_id`.
Idempotent (`NOT EXISTS` guard). 291 inserts, 291 active leads —
the sanity counts matched.

**Not in scope for this ADR.** The `/api/leads/{id}/stage-durations`
endpoint added in Sprint Lead Card v2 (PR #45) consumes the table
for one lead at a time. Workspace-wide analytics is on the roadmap
but not built yet.

## ADR-026 `leads.primary_contact_id` is a pin, not a role

**Date:** 2026-05-15
**Status:** ✅ (Sprint Lead Card Redesign, PR [#41](https://github.com/GlobalSasha/crm/pull/41))

**Decision.** A lead has at most one «основной ЛПР» pinned via
`leads.primary_contact_id UUID NULL FK → contacts.id ON DELETE SET
NULL`. This is **independent of** the existing
`contacts.role_type` ENUM (`economic_buyer / champion /
technical_buyer / operational_buyer`).

The two answer different questions:

- `contacts.role_type` — what KIND of stakeholder this person is
  (BANT-style decision-maker role). Many roles per lead are normal:
  one economic buyer + one champion + one technical.
- `leads.primary_contact_id` — who is the manager's MAIN point of
  contact right now. UI surfaces this in the pipeline card and the
  LeadCard header («★ Иванов И.И.»). Always at most one per lead.

**Why not promote one role to «primary».** Tried it on paper —
`primary_role` boolean on `contacts`, or a sentinel role value like
`primary_economic_buyer`. Both bled the «kind of stakeholder» axis
into the «who is the manager working with» axis and made gate
checks (ADR-012 — Economic Buyer required at Stage 6) harder to
reason about. Two separate concerns, two separate columns.

**Set / unset flow.** `PATCH /leads/{lead_id}/primary-contact` body
`{contact_id?}`. Server validates `contact.lead_id == lead_id` so
a UUID forged from another lead can't be promoted. Pass `null` to
clear. Setting a new contact automatically replaces the previous —
single FK column, no «which one is primary» bookkeeping needed.

**Side-effect on ORM.** Adding `Lead.primary_contact_id` created a
second FK path between `leads` ⇄ `contacts` (the original being
`Contact.lead_id` → `leads.id`). SQLAlchemy then refused to resolve
`Contact.lead`'s back-populates and crashed mapper init on every
request — production took a 500 outage for ~10 minutes before
PR #43 hot-fixed it with explicit `foreign_keys="Contact.lead_id"`
on both sides of the relationship. **If you ever add another
cross-domain FK between two existing tables, write the
`foreign_keys=` pin in the same commit — don't trust SQLAlchemy
to disambiguate.**
