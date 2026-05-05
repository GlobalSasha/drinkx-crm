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
| ADR-008 | DeepSeek V3 primary, GPT-4o for vision/high-value | ✅ |
| ADR-009 | Package-per-domain backend (not layered) | ✅ |
| ADR-010 | Rotting = two independent rules | ✅ |
| ADR-011 | Pilot Success Contract activates at Stage 9 | ✅ |
| ADR-012 | Economic Buyer required from Stage 6 | ✅ |
| ADR-013 | Bare-metal hosting (not Vercel/Railway) | ✅ |
| ADR-014 | Stub-mode auth before Supabase keys | ✅ |
| ADR-015 | Lead Pool + Weekly Sprint System (PRD-addition v2.1) | ✅ |
| ADR-016 | B2B model (index-b2b.html) is official target; PRD v2.0 outdated | ✅ |
| ADR-017 | Scoring criteria = separate table `scoring_criteria`, per-workspace | ✅ |

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

## ADR-008 DeepSeek V3 primary, GPT-4o for vision + high-value only
Cost: DeepSeek ~$0.0003/1K tokens vs GPT-4o ~$0.01/1K (33× cheaper).
GPT-4o reserved for: visit-card OCR (vision), fit≥8 re-enrichment (premium).
Gemini 1.5 Pro as fallback if both fail.

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
