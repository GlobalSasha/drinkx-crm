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
| ADR-021 | Single-workspace model — bootstrap joins existing | ✅ |
| ADR-022 | `agent_state` lives on the lead row (JSONB), not in a separate table | ✅ |
| ADR-023 | Lead Agent is named «Чак» — never «AI» / «ИИ» / «языковая модель» in user-facing text | ✅ |
| ADR-024 | Brand-accent is `#FF4E00` (DrinkX orange), not `#1F4D3F` (legacy green) | ✅ |
| ADR-025 | Activity-first lead card — default tab is `activity`, not `deal` | ✅ |
| ADR-026 | Lead-agent knowledge files co-located with the API package | ✅ |

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

## ADR-022 `agent_state` lives on the lead row (JSONB), not a separate table

Date: 2026-05-10
Status: ✅
Sprint: 3.1 Phase B (migration `0022_lead_agent_state`)

Lead Agent state — current banner suggestion, last-analyzed activity
id, coach session counter, future SPIN-phase / silence-alert
timestamps — is stored on `leads.agent_state JSONB NOT NULL DEFAULT
'{}'`. No separate `lead_agent_states` table.

**Why JSONB on the lead, not a sibling table:**
- One-to-one with `leads`. A separate table would be a 1:1 join on
  every lead-card load, added without paying for a many-to-one
  relationship anywhere.
- Suggestion is a single current value, not a history. The
  «suggestions log» from the Sprint 3.1 spec is intentionally
  capped at the latest one in v1; longer history (for accept/ignore
  rate metrics) is a Sprint 3.2+ concern and can move to a
  `lead_agent_events` log table when that need is real.
- Coach chat history lives **on the client** (in-component state in
  `SalesCoachDrawer.tsx`), explicitly ephemeral. Persisting it would
  trigger a privacy decision the team hasn't made.

**Schema is opaque at the DB level.** The Pydantic shape (`AgentState`
in `app/lead_agent/schemas.py`) can evolve without a migration as
long as field additions are non-required and removals are tolerant
of legacy keys. Existing rows backfilled to `{}` via `server_default`.

**Trade-off:** can't index on `agent_state` keys without a
GIN/expression index later. Acceptable in v1 — every read is
single-lead anyway, indexed by `leads.id` PK.

## ADR-023 Lead Agent is named «Чак», never «AI» in user-facing text

Date: 2026-05-10
Status: ✅
Sprint: 3.1 (knowledge files + UI strings)

Across UI labels, system prompts, banner copy, drawer header, and
documentation visible to managers, the agent is called **Чак** — not
«AI», «ИИ», «языковая модель», «алгоритм», «бот», «ассистент»
(generic), or any other technical synonym.

**Why a name, not a category:**
- B2B managers run high-stakes conversations. A consistent named
  collaborator («Чак говорит, что у клиента нет Economic Buyer»)
  reads as a peer suggestion; «AI говорит» reads as a
  recommendation from a black box that the manager will instinctively
  discount.
- Russian UX writing benefits from a single short subject. «Чак»
  keeps banners and chat replies under the line-budget that «AI-
  ассистент» eats up.
- Pre-empts the «AI-disclaimer» reflex (every reply prefixed with
  «Как языковая модель…») — the system prompt explicitly forbids it.

**Where this binds:**
- `apps/api/knowledge/agent/lead-ai-agent-skill.md` — system prompt
  enforces tone + first-person framing.
- `apps/api/app/lead_agent/prompts.py` — both `SUGGESTION_SYSTEM` and
  `CHAT_SYSTEM` open with «Ты — Чак, персональный ассистент менеджера
  по продажам DrinkX.»
- `apps/web/components/lead-card/AgentBanner.tsx` — caption reads
  «рекомендация чака».
- `apps/web/components/lead-card/SalesCoachDrawer.tsx` — header «Чак ·
  Sales Coach».
- LeadCard FAB — «🤖 AI Coach» (the only public surface that still
  carries «AI» — kept as the entry-point label so users coming from
  CRM jargon can find the feature; once they open the drawer, they
  meet Чак). Open question whether to rename the button to «Чак»;
  parked.

Internal code uses `lead_agent` package name and `AgentSuggestion` /
`AgentChat*` schema names — internal identifiers stay technical.

## ADR-024 Brand-accent is `#FF4E00`, not `#1F4D3F`

Date: 2026-05-10
Status: ✅
Sprint: «UI/Design System overhaul» (May 2026, PRs #4 + carryovers)

DrinkX brand color is **`#FF4E00`** (orange). The CRM's pre-Sprint-3.0
codebase used `#1F4D3F` (dark green) as the accent — a placeholder
from early prototyping that drifted into production. The Sprint 3.0
UI overhaul (PR [#4](https://github.com/GlobalSasha/drinkx-crm/pull/4)
+ subsequent fix-ups in PRs #5–#10) replaces it with the brand
palette.

**Token plumbing:**
- `apps/web/tailwind.config.ts` — `colors.brand.{accent, accent-text, accent-soft, primary, muted, muted-strong, muted-light, border, panel, bg, soft, canvas}` defined as the source of truth.
- `apps/web/app/globals.css` — CSS variables `--brand-accent`, `--brand-soft`, etc. mirror the Tailwind values for non-Tailwind contexts (Tabler icons, third-party widgets).
- `apps/web/lib/design-system.ts` — `C.color`, `C.button`, `C.form`, `C.bodyXs/Sm`, `C.btn/btnLg`, `C.metricSm`, `C.caption`. New components compose from `C.*` instead of hand-rolling utility strings.
- `apps/web/lib/ui/priority.ts` — A/B/C/D priority chips re-mapped to the brand-accent ramp (Sprint 2.4 G5 carryover).

**Migration policy:**
- Old tokens (`bg-canvas`, `text-ink`, `text-accent` green, `bg-accent` green) **kept** in Tailwind config for back-compat — touching every component at once was infeasible.
- New components / new screens **must** compose from `C.*` and `bg-brand-*` / `text-brand-*` only.
- Existing screens migrated opportunistically: every Today / LeadCard / Pipeline change lands under the new palette. Three screens are still on legacy tokens at the time of this ADR — see `docs/brain/04_NEXT_SPRINT.md` priority 2.

**Why a hard switch and not a per-screen feature flag:**
The accent leaks across components — a Pipeline header on the brand
palette next to a Settings page on the legacy palette is jarring and
makes the old screens feel broken. One-shot switch + opportunistic
migration > coexistence.

## ADR-025 Activity-first lead card — default tab is `activity`

Date: 2026-05-10
Status: ✅
Sprint: 3.0 UI overhaul (PR [#14](https://github.com/GlobalSasha/drinkx-crm/pull/14))

When a manager opens `/leads/[id]`, the default tab is **«Активность»**
(`activeTab='activity'`), not «Сделка» (`'deal'`). Deep-link
`?tab=deal` overrides the default and continues to work.

**Why:**
- A manager comes to a lead card to **do** — write the next message,
  log a call, see the last reply, set the next step — not to read
  the deal parameters again. The activity feed is the working
  surface; the deal tab is reference data.
- The «Следующий шаг» commitment also moved into the Activity tab
  (PR #14): saving it persists `lead.next_step` AND mirrors the same
  text as a `task` activity in the feed. The two operations are now
  one action on one screen.
- A/B/C/D priority, score, blocker, and deal type — the things on
  the «Сделка» tab — change weekly at most. Stale-anchored content
  doesn't belong on the landing tab.

**Implementation:**
- `apps/web/components/lead-card/LeadCard.tsx` — `initialTab` falls
  back to `'activity'` if `?tab=` is missing or invalid.
- `ActivityTab` accepts the full `lead: LeadOut` (was just `leadId`)
  so it can seed the «Следующий шаг» inputs from the current row.
- `DealTab` no longer renders the «СЛЕДУЮЩИЙ ШАГ / СРОК» grid — the
  state and handlers were dropped, sync effect cleaned up.

## ADR-026 Lead-agent knowledge files co-located with the API package

Date: 2026-05-10
Status: ✅
Sprint: 3.1 (PR [#20](https://github.com/GlobalSasha/drinkx-crm/pull/20))

Lead Agent reads two knowledge files at runtime — **product
foundation** (DrinkX product context) and **skill** (behavioural
spec, SPIN methodology, output formats). Both live at:

```
apps/api/knowledge/agent/product-foundation.md
apps/api/knowledge/agent/lead-ai-agent-skill.md
```

The earlier placement at repo `docs/skills/` and `docs/knowledge/agent/`
was outside the API Docker build context (`apps/api/`), so on
production the runner fell into its soft-fail branch and prompts
shipped without the foundation block — degraded but functional.

**Why co-locate, not change the build context:**
- `apps/api/Dockerfile` already had `COPY knowledge ./knowledge` (the
  enrichment KB has lived there since Sprint 1.3). Adding the agent
  knowledge under the same root reaches the container at
  `/app/knowledge/agent/...` with **zero** Dockerfile or `docker-compose.yml`
  change.
- Keeping the build context at `apps/api/` keeps the API image
  surgical: it doesn't drag the whole monorepo (web sources, infra
  docker files, ADRs) into the api/worker/beat layers.

**Reader contract:**
- `app/lead_agent/context.py` walks ancestors of `__file__` looking
  for the first directory that contains
  `knowledge/agent/product-foundation.md`. In dev that's `apps/api/`;
  in prod that's `/app`. The walker is wrapped in `lru_cache(maxsize=1)`
  so each worker process resolves once at boot.
- `_read_relative()` returns `""` when the file isn't reachable
  (renamed deploy layout, tests running from a stripped-down context),
  with a one-time `lead_agent.knowledge.root_missing` warning. The
  runner falls back to a foundation-less prompt and labels the agent
  output as still functional but degraded.

**Trade-off:** the spec doc `docs/SPRINT_3_1_LEAD_AI_AGENT.md`
historically said «`docs/...` paths». PR #20 updated the spec to
match — the canonical path is the runtime location.
