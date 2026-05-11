# RECON — Lead Card schema (Variant B, source-only)

**Date:** 2026-05-11
**Mode:** Variant B — schema extracted from ORM models + Alembic migrations only.
**Source files inspected:**
- `apps/api/app/leads/models.py`
- `apps/api/app/contacts/models.py`
- `apps/api/app/activity/models.py`
- `apps/api/app/enrichment/schemas.py` (Pydantic `ResearchOutput`)
- `apps/api/app/enrichment/orchestrator.py` (single writer of `lead.ai_data`)
- `apps/api/app/auth/models.py` (`ScoringCriteria`)
- All migrations `apps/api/alembic/versions/20260505_0001..20260510_0022_*.py`
- `apps/web/components/lead-card/{LeadCard,DealTab,ScoringTab,AIBriefTab}.tsx` (write-paths verification)

**No live DB access.** Coverage stats (queries 4, 6) and `ai_data` samples (query 2) are **not** in this report — they require either a SQL session against `drinkx-postgres-1` or a Supabase tunnel.

---

## Section 1 — `leads` table columns

Schema below is the union of migration `0002_b2b_model` (creates the table)
and `0022_lead_agent_state` (adds `agent_state`). All other migrations
0003–0021 do **not** touch `leads`. ORM model in
`apps/api/app/leads/models.py` matches.

| # | name | type | nullable | default | notes |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NO | — | PK |
| 2 | `created_at` | timestamptz | NO | `now()` | from `TimestampedMixin` |
| 3 | `updated_at` | timestamptz | NO | `now()` | from `TimestampedMixin` |
| 4 | `workspace_id` | UUID | NO | — | FK `workspaces.id` ON DELETE CASCADE, indexed |
| 5 | `pipeline_id` | UUID | YES | NULL | FK `pipelines.id` ON DELETE SET NULL |
| 6 | `stage_id` | UUID | YES | NULL | FK `stages.id` ON DELETE SET NULL |
| 7 | `company_name` | varchar(255) | NO | — | GIN FTS index `ix_leads_company_name_fts` |
| 8 | `segment` | varchar(60) | YES | NULL | |
| 9 | `city` | varchar(120) | YES | NULL | |
| 10 | `email` | varchar(254) | YES | NULL | |
| 11 | `phone` | varchar(30) | YES | NULL | |
| 12 | `website` | varchar(512) | YES | NULL | |
| 13 | `inn` | varchar(20) | YES | NULL | |
| 14 | `source` | varchar(60) | YES | NULL | provenance chip (`form:slug`, `import:bitrix`, `manual`, ...) |
| 15 | `tags_json` | JSON | NO | `'[]'::json` | list of strings |
| 16 | `deal_type` | varchar(30) | YES | NULL | enum: `enterprise_direct`, `qsr`, `distributor_partner`, `raw_materials`, `private_small`, `service_repeat` |
| 17 | `priority` | varchar(2) | YES | NULL | enum: `A` / `B` / `C` / `D` |
| 18 | `score` | int | NO | `0` | **0–100** — manual ScoringTab output (Σ(value/max × weight)) |
| 19 | `fit_score` | numeric(4,2) | YES | NULL | **0.0–10.0** — AI ICP match from Research Agent |
| 20 | `assignment_status` | varchar(20) | NO | `'pool'` | enum: `pool` / `assigned` / `transferred` |
| 21 | `assigned_to` | UUID | YES | NULL | FK `users.id` ON DELETE SET NULL |
| 22 | `assigned_at` | timestamptz | YES | NULL | |
| 23 | `transferred_from` | UUID | YES | NULL | FK `users.id` ON DELETE SET NULL |
| 24 | `transferred_at` | timestamptz | YES | NULL | |
| 25 | `next_action_at` | timestamptz | YES | NULL | rotting input |
| 26 | `last_activity_at` | timestamptz | YES | NULL | rotting input + Lead Agent silence trigger |
| 27 | `is_rotting_stage` | bool | NO | `false` | **see §5** — read but never written internally |
| 28 | `is_rotting_next_step` | bool | NO | `false` | **see §5** — read but never written internally |
| 29 | `pilot_contract_json` | JSON | YES | NULL | **see §5** — no writers found |
| 30 | `blocker` | varchar(500) | YES | NULL | exposed in `LeadCreate`/`LeadUpdate` schemas; user-input only |
| 31 | `next_step` | varchar(500) | YES | NULL | same |
| 32 | `archived_at` | timestamptz | YES | NULL | |
| 33 | `won_at` | timestamptz | YES | NULL | |
| 34 | `lost_at` | timestamptz | YES | NULL | |
| 35 | `lost_reason` | varchar(500) | YES | NULL | |
| 36 | `ai_data` | JSON | YES | NULL | Research Agent output — shape in §2 |
| 37 | `agent_state` | JSONB | NO | `'{}'::jsonb` | Sprint 3.1 Lead AI Agent memory (SPIN phase, suggestion log, silence alerts). Schema owned by `app/lead_agent/schemas.py:AgentState` |

**Indexes:**
- `ix_leads_workspace_id` on (`workspace_id`)
- `ix_leads_workspace_stage` on (`workspace_id`, `stage_id`)
- `ix_leads_workspace_assignment` on (`workspace_id`, `assignment_status`)
- `ix_leads_rotting` on (`is_rotting_stage`, `is_rotting_next_step`)
- `ix_leads_company_name_fts` GIN on `to_tsvector('simple', company_name)`

---

## Section 2 — `ai_data` JSON schema

**Definition:** Pydantic `ResearchOutput` in `apps/api/app/enrichment/schemas.py`.
**Writer:** `apps/api/app/enrichment/orchestrator.py:701` —
`lead.ai_data = research_output.model_dump()`. Only one writer (plus
`import_export/diff_engine.py:443` which round-trips arbitrary AI bulk-update
payloads — not authoritative).

| key | type | default | notes |
|---|---|---|---|
| `company_profile` | str | `""` | 2–3 sentence business summary |
| `network_scale` | str | `""` | |
| `geography` | str | `""` | |
| `formats` | `list[str] \| str` | `[]` | LLMs sometimes return a single string; frontend handles both |
| `coffee_signals` | `list[str] \| str` | `[]` | same |
| `growth_signals` | `list[str]` | `[]` | |
| `risk_signals` | `list[str]` | `[]` | |
| `decision_maker_hints` | `list[DecisionMakerHint]` | `[]` | items: `{name, title, role, confidence, source}` — see sub-schema |
| `contacts_found` | `list[FoundContact]` | `[]` | items: `{name, title?, email?, phone?, linkedin_url?, source, confidence: float 0–1}` — these are auto-materialised into `contacts` rows with `verified_status='to_verify'` above the 0.5 threshold (orchestrator does the materialisation) |
| `fit_score` | float | `0.0` | 0.0–10.0; ALSO written to `lead.fit_score` column |
| `next_steps` | `list[str]` | `[]` | |
| `urgency` | str | `""` | canonical: `"high" / "medium" / "low" / ""` |
| `sources_used` | `list[str]` | `[]` | |
| `notes` | str | `""` | |
| `score_rationale` | str | `""` | 2–3 sentences explaining why this fit_score (rendered on AIBriefTab) |

**`DecisionMakerHint`** sub-schema:
| key | type | default |
|---|---|---|
| `name` | str | `""` |
| `title` | str | `""` |
| `role` | str | `""` (canonical: `economic_buyer / champion / technical_buyer / operational_buyer`) |
| `confidence` | str | `"low"` (canonical: `high / medium / low`) |
| `source` | str | `""` |

All fields have defaults — schema never raises on missing input
(per PRD §7.2 hard requirement).

---

## Section 3 — `contacts` table columns

Source: migration `0002_b2b_model` + `apps/api/app/contacts/models.py`. No
later migration touches `contacts`.

| # | name | type | nullable | default | notes |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NO | — | PK |
| 2 | `created_at` | timestamptz | NO | `now()` | |
| 3 | `updated_at` | timestamptz | NO | `now()` | |
| 4 | `lead_id` | UUID | NO | — | FK `leads.id` ON DELETE CASCADE, indexed |
| 5 | `name` | varchar(120) | NO | — | |
| 6 | `title` | varchar(120) | YES | NULL | |
| 7 | `role_type` | varchar(30) | YES | NULL | enum: `economic_buyer / champion / technical_buyer / operational_buyer` |
| 8 | `email` | varchar(254) | YES | NULL | |
| 9 | `phone` | varchar(30) | YES | NULL | |
| 10 | `telegram_url` | varchar(255) | YES | NULL | |
| 11 | `linkedin_url` | varchar(255) | YES | NULL | |
| 12 | `source` | varchar(40) | YES | NULL | e.g. `research_agent`, `manual` |
| 13 | `confidence` | varchar(20) | NO | `'medium'` | `high / medium / low` |
| 14 | `verified_status` | varchar(20) | NO | `'to_verify'` | `verified / to_verify` — AI-found contacts always land as `to_verify` |
| 15 | `notes` | text | YES | NULL | |

**Index:** `ix_contacts_lead_id` on (`lead_id`).

---

## Section 4 — `activities` table columns

Source: migration `0002_b2b_model` (initial) + `0009_inbox_items_and_activity_email` (email fields, widen `subject`). ORM model in `apps/api/app/activity/models.py`.

| # | name | type | nullable | default | notes |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NO | — | PK |
| 2 | `created_at` | timestamptz | NO | `now()` | |
| 3 | `updated_at` | timestamptz | NO | `now()` | |
| 4 | `lead_id` | UUID | NO | — | FK `leads.id` ON DELETE CASCADE, indexed |
| 5 | `user_id` | UUID | YES | NULL | FK `users.id` ON DELETE SET NULL — audit trail, not visibility filter (ADR-019) |
| 6 | `type` | varchar(30) | NO | — | enum: `comment / task / reminder / file / email / tg / system / stage_change / score_update / form_submission` |
| 7 | `payload_json` | JSON | NO | `'{}'::json` | type-specific carrier (form submission UTM, score deltas, etc.) |
| 8 | `task_due_at` | timestamptz | YES | NULL | |
| 9 | `task_done` | bool | NO | `false` | |
| 10 | `task_completed_at` | timestamptz | YES | NULL | |
| 11 | `reminder_trigger_at` | timestamptz | YES | NULL | |
| 12 | `file_url` | varchar(512) | YES | NULL | |
| 13 | `file_kind` | varchar(40) | YES | NULL | |
| 14 | `channel` | varchar(20) | YES | NULL | `email / tg / phone / ...` |
| 15 | `direction` | varchar(10) | YES | NULL | `in / out` |
| 16 | `subject` | varchar(500) | YES | NULL | widened 300→500 in 0009 |
| 17 | `body` | text | YES | NULL | |
| 18 | `gmail_message_id` | varchar(200) | YES | NULL | partial-unique index `ix_activities_gmail_message_id` WHERE NOT NULL |
| 19 | `gmail_raw_json` | JSON | YES | NULL | original Gmail payload (skipped if >50KB) |
| 20 | `from_identifier` | varchar(300) | YES | NULL | |
| 21 | `to_identifier` | varchar(300) | YES | NULL | |

**Indexes:**
- `ix_activities_lead_id` on (`lead_id`)
- `ix_activities_lead_type` on (`lead_id`, `type`)
- `ix_activities_gmail_message_id` UNIQUE on (`gmail_message_id`) WHERE `gmail_message_id IS NOT NULL`

---

## Section 5 — fields likely empty in prod

Detection method: `grep -rn "\.<col>\s*=" apps/api/app/` plus inspection of
schemas. A column counts as "likely empty" if there is no internal writer
**and** it is not exposed for user input in `LeadCreate`/`LeadUpdate`.

| field | status | evidence |
|---|---|---|
| `leads.pilot_contract_json` | **Likely empty** — no writers anywhere. Defined in migration 0002; mentioned only in `models.py`. Sprint 1.2 plumbed the column but never built the Pilot Success Contract editor. The frontend `PilotTab.tsx` reads from it but has no write-path that touches this column. |
| `leads.is_rotting_stage` | **Likely all `false`** — read by `daily_plan/priority_scorer.py:68`, but no setter exists in any service / Celery task / route. Default is `false`; defaults to `false` for every row. (The rotting indicator on the UI is therefore effectively dead in prod.) |
| `leads.is_rotting_next_step` | **Likely all `false`** — same as above. |
| `leads.transferred_from` | **Likely sparse** — written exactly once, by the Передать (transfer) modal flow in `leads/services.py`. Most leads never get transferred → NULL. |
| `leads.transferred_at` | **Likely sparse** — same as above. |
| `leads.blocker` | **User-input only.** Exposed in `LeadCreate`/`LeadUpdate` schemas. No internal automation writes it. Likely sparse unless managers explicitly fill it. |
| `leads.next_step` | **User-input only.** Same as `blocker`. |
| `leads.lost_reason` | **User-input only** via LostModal (Sprint 2.6). Populated only for `lost_at IS NOT NULL` rows. |
| `leads.archived_at` | **User-input only** via archive action. Likely few rows. |
| `leads.score` | **Likely 0 for most rows** — only writer is `ScoringTab.tsx` (manual). Default is `0`. AI never sets it. |
| `leads.fit_score` | **Populated only for AI-enriched rows** — the orchestrator writes it. Lead Pool query uses `nullslast(fit_score.desc())` so NULLs are expected. |
| `leads.ai_data` | **Populated only for AI-enriched rows** — same trigger as `fit_score`. |

**Confirmed-populated columns** (writers exist in code): `workspace_id`,
`pipeline_id`, `stage_id`, `company_name`, `segment`, `city`, `email`,
`phone`, `website`, `inn`, `source`, `tags_json`, `deal_type`, `priority`,
`assignment_status`, `assigned_to`, `assigned_at`, `next_action_at`,
`last_activity_at`, `won_at`, `lost_at`, `agent_state` (after first agent fire).

---

## Section 6 — what `data.js` has that the CRM schema does NOT

`data.js` here = `/Users/aleksandrhvastunov/Desktop/crm-prototype/data.js`.
All thirteen listed keys exist in that file (verified via grep). The
question is whether the CRM has a place to put them today.

| `data.js` field | CRM mapping | Status |
|---|---|---|
| `company_overview` | `ai_data.company_profile` (semantic match, name differs) | **Rename mismatch.** Importer would need a translation step. Prototype is the longer marketing-style overview; CRM schema name is `company_profile`. |
| `network_scale` | `ai_data.network_scale` | ✅ Direct mapping. |
| `geography` | `ai_data.geography` | ✅ Direct mapping. |
| `formats` | `ai_data.formats` | ✅ Direct mapping. CRM accepts `list[str] \| str`. |
| `coffee_signals` | `ai_data.coffee_signals` | ✅ Direct mapping. CRM accepts `list[str] \| str`. |
| `sales_triggers` | (none) | ❌ **No mapping.** Closest semantic neighbour is `ai_data.growth_signals` (which is about company growth, not sales triggers). Would need either a rename or a new `ai_data` key. |
| `entry_route` | (none) | ❌ **No mapping.** Prototype-specific "how to approach this lead" narrative. Closest is `ai_data.next_steps[]` but that's a checklist, not a strategy paragraph. |
| `research_gaps` | (none) | ❌ **No mapping.** "What we still need to find out" — closest is `ai_data.notes` but that's free-form, no semantic guarantee. |
| `people_to_verify` | `ai_data.decision_maker_hints[]` (semantic — these are unverified leads) | **Partial.** `decision_maker_hints` has the right shape (`{name, title, role, confidence, source}`) but lacks the prototype's distinction between "verified people" and "people to verify". CRM puts verification on the `contacts` table via `verified_status` instead. |
| `source_links_md` | `ai_data.sources_used[]` | **Partial.** CRM stores plain URL list; prototype stores markdown with anchor text. Importer would need to flatten. |
| `linkedin_contacts` | `contacts.linkedin_url` (per-contact column) | **Partial.** CRM puts LinkedIn at the contact granularity, not at the lead-level. Importer would need to fan out into `contacts` rows. |
| `industry_signals` | (none) | ❌ **No mapping.** Distinct from `growth_signals` in the prototype's intent (industry-wide vs company-specific). No CRM key matches. |
| `industry_people` | (none) | ❌ **No mapping.** Industry-level personalia, not company-level decision-makers. |

**Grep verification:** none of `company_overview`, `sales_triggers`,
`entry_route`, `research_gaps`, `people_to_verify`, `source_links_md`,
`linkedin_contacts`, `industry_signals`, `industry_people` appear anywhere
in `apps/api/` or `apps/web/`. Six of the thirteen prototype fields have
no home in production today.

---

## Section 7 — scoring table

**Two distinct numbers, two distinct sources of truth.**

### `score` (0–100) — manual ScoringTab

- **Storage:** `leads.score` (int, NOT NULL, default 0).
- **Writer:** frontend `apps/web/components/lead-card/ScoringTab.tsx:44` —
  `updateLead.mutate({ score: total })` where
  `total = Σ((value/max_value) * weight)` computed client-side.
- **No AI writer.** No backend automation writes this column.
- **Likely 0 for most rows** unless a manager opened ScoringTab and saved.

### `fit_score` (0.0–10.0) — AI ICP match

- **Storage:** `leads.fit_score` (numeric(4,2), nullable).
- **Writer:** `apps/api/app/enrichment/orchestrator.py:703` —
  `lead.fit_score = research_output.fit_score` after a successful Research
  Agent run.
- **Also persisted inside** `ai_data.fit_score` (same number, two
  homes — known issue `00_CURRENT_STATE.md` §"Known issues" item 4:
  "last-writer-wins, no conflict resolution").

### `scoring_criteria` table — weights, not values

Source: migration `0002_b2b_model` + ORM `apps/api/app/auth/models.py:130`.

Table: `scoring_criteria`
| column | type | nullable | default |
|---|---|---|---|
| `id` | UUID | NO | — |
| `workspace_id` | UUID | NO | (FK workspaces ON DELETE CASCADE, indexed) |
| `criterion_key` | varchar(60) | NO | — |
| `label` | varchar(120) | NO | — |
| `weight` | int | NO | — |
| `max_value` | int | NO | `5` |

UNIQUE (`workspace_id`, `criterion_key`).

**Seeded per workspace** in migration 0002. Default 8 criteria, total weight = 100:

| criterion_key | label | weight | max_value |
|---|---|---|---|
| `scale_potential` | Масштаб потенциала | 20 | 5 |
| `pilot_probability_90d` | Вероятность пилота 90д | 15 | 5 |
| `economic_buyer` | Экономический покупатель | 15 | 5 |
| `reference_value` | Референсная ценность | 15 | 5 |
| `standard_product` | Стандартный продукт | 10 | 5 |
| `data_readiness` | Готовность данных | 10 | 5 |
| `partner_potential` | Партнёрский потенциал | 10 | 5 |
| `budget_confirmed` | Бюджет подтверждён | 5 | 5 |

**Important:** `scoring_criteria` defines the **weights and labels per
workspace**. The **per-lead values** that the manager picks on ScoringTab
are NOT stored in a separate table — they're never persisted. ScoringTab
recomputes them from the criteria (with values held in component state)
and writes only the rolled-up `lead.score` total. So in prod we have:
- the criteria definitions (likely 8 rows × N workspaces),
- the final `lead.score` int,
- **no per-criterion answer** persisted anywhere.

If the new Lead Card prototype wants to show "you scored 4/5 on
`pilot_probability_90d`", that data does not exist in the DB — only the
total survives.

---

## Gaps left by Variant B

Because this report came from source code, not a live DB, the following
queries from the original task spec are **NOT** in this file:

- **Query 2** — Sample `ai_data` from a non-empty lead. (Real LLM output
  often deviates from the schema; the actual stored JSON may include
  extra keys the Pydantic model accepts silently, or omit keys the
  schema would auto-default.)
- **Query 4** — Coverage stats (`with_ai_data`, `with_score > 0`,
  `with_fit_score`, `total_leads`). The §5 "likely empty" calls are
  inferences from grep, not measurements.
- **Query 5** — One full lead row. Same as query 4.
- **Query 6** — Contacts-per-lead average. The codebase confirms the
  cardinality is 1-lead-to-many-contacts; the actual ratio in prod is
  unknown.

To close these gaps either:
1. Approve SSH to `deploy@crm.drinkx.tech` (add Bash permission rule),
   then run `docker exec drinkx-postgres-1 psql -U drinkx -d drinkx_crm
   -c "<query>"`, or
2. Provide a direct Postgres connection string (port-forward or
   tunnel) and the recon agent will connect by `psql` and append the
   missing sections to this report.

> **UPDATE 2026-05-11:** SSH access granted (`ssh drinkx-crm`, container
> `drinkx-postgres-1`, user `drinkx`, db `drinkx_crm`). Live results
> appended below in §8.

---

## Section 8 — Live DB results

Run via `ssh drinkx-crm 'docker exec drinkx-postgres-1 psql -U drinkx
-d drinkx_crm -c "<query>"'`. Raw psql output verbatim.

### Q1 — `leads` columns

```
     column_name      |        data_type         | is_nullable
----------------------+--------------------------+-------------
 id                   | uuid                     | NO
 created_at           | timestamp with time zone | NO
 updated_at           | timestamp with time zone | NO
 workspace_id         | uuid                     | NO
 pipeline_id          | uuid                     | YES
 stage_id             | uuid                     | YES
 company_name         | character varying        | NO
 segment              | character varying        | YES
 city                 | character varying        | YES
 email                | character varying        | YES
 phone                | character varying        | YES
 website              | character varying        | YES
 inn                  | character varying        | YES
 source               | character varying        | YES
 tags_json            | json                     | NO
 deal_type            | character varying        | YES
 priority             | character varying        | YES
 score                | integer                  | NO
 fit_score            | numeric                  | YES
 assignment_status    | character varying        | NO
 assigned_to          | uuid                     | YES
 assigned_at          | timestamp with time zone | YES
 transferred_from     | uuid                     | YES
 transferred_at       | timestamp with time zone | YES
 next_action_at       | timestamp with time zone | YES
 last_activity_at     | timestamp with time zone | YES
 is_rotting_stage     | boolean                  | NO
 is_rotting_next_step | boolean                  | NO
 pilot_contract_json  | json                     | YES
 blocker              | character varying        | YES
 next_step            | character varying        | YES
 archived_at          | timestamp with time zone | YES
 won_at               | timestamp with time zone | YES
 lost_at              | timestamp with time zone | YES
 lost_reason          | character varying        | YES
 ai_data              | json                     | YES
 agent_state          | jsonb                    | NO
(37 rows)
```

**Confirms §1.** 37 columns, identical to the migration-derived list.

### Q2 — sample `ai_data` (2 non-empty leads)

Row 1 — **`Аптека Апрель`** (prototype-import shape):

```json
{
  "company_overview": "Одна из крупнейших аптечных сетей России, основана в 2000 году в Краснодаре. Специализируется на розничной торговле лекарствами, средствами ухода, медицинскими изделиями, косметикой, витаминами. Оборот группы компаний ~194 млрд руб. (2024), ~22 000 сотрудников. Также развивает бренды «Аптечный клуб» и «Аптечный склад».",
  "network_scale": "Более 8000-10500 аптек (данные 2024-2025 гг.)",
  "geography": "77 регионов России, включая Краснодарский край, Москву/область, Волгоград, Астрахань, Крым, Челябинск и многие другие.",
  "formats": "Аптеки-дискаунтеры («Аптечный склад»), аптечные маркеты с открытой выкладкой, семейные аптеки.",
  "coffee_signals": "Нет упоминаний кофе, кофе-то-го, кафе, foodservice или ready-to-eat в аптеках. Аптеки расположены в ТЦ рядом с кафе, но без собственных сервисов.",
  "sales_triggers": [
    "Масштабная федеральная сеть с быстрой экспансией (постоянно открывает новые аптеки в регионах)",
    "Программа лояльности с миллионами карт - возможность кросс-продаж",
    "Лидер рынка по продажам (1-е место в 2024)"
  ],
  "entry_route": "Связаться с отделом партнерств/закупок через официальный сайт или соцсети (Telegram/VK), предложить пилот кофейных станций в высокотрафиковых аптеках для сотрудников/клиентов.",
  "research_gaps": "Детальные контакты коммерческого директора/закупок/category manager food/non-pharma; точное текущее число аптек (диапазон из источников); наличие/отсутствие foodservice подтверждено косвенно - нужны тендеры/закупки.\"",
  "confidence": "High",
  "source_id": "аптека-апрель"
}
```

Row 2 — **`Перекрёсток (Perekrestok)`** (ResearchOutput shape):

```json
{
  "company_profile": "Крупнейшая сеть супермаркетов в России, входит в X5 Group. Насчитывает более 1000 магазинов в Москве, регионах и онлайн-доставку.",
  "network_scale": "1000+ магазинов",
  "geography": "Москва, Московская область, регионы России",
  "formats": ["супермаркет", "онлайн-доставка"],
  "coffee_signals": [],
  "growth_signals": [
    "активное развитие онлайн-доставки",
    "постоянное расширение сети"
  ],
  "risk_signals": [
    "крупная федеральная сеть с централизованными закупками — высокий порог входа"
  ],
  "decision_maker_hints": [],
  "contacts_found": [],
  "fit_score": 8.0,
  "next_steps": [
    "Найти контакт категорийного менеджера по готовой еде или напиткам через LinkedIn или базу X5 Group",
    "Подготовить предложение с акцентом на подписную модель и удалённый мониторинг для снижения операционной нагрузки",
    "Проверить, есть ли в магазинах Перекрёстка кофейные станции конкурентов (например, NeoCoffee) через мониторинг точек"
  ],
  "urgency": "medium",
  "sources_used": [
    "https://www.perekrestok.ru/",
    "https://ru.wikipedia.org/wiki/Перекрёсток_(сеть_магазинов)",
    "https://rabota.perekrestok.ru/"
  ],
  "notes": "Крупный клиент, но без прямых сигналов о кофе. Рекомендуется холодный контакт через категорийного менеджера.",
  "score_rationale": "Сеть из 1000+ точек — идеальный масштаб для DrinkX. Высокий трафик и развитая foodservice-зона в супермаркетах создают спрос на кофе. Однако отсутствие явных сигналов о заинтересованности в self-service кофе и централизованные закупки требуют квалификации."
}
```

> **Critical finding — §6 needs revision.** Production `ai_data` is **not
> homogeneous**. We have at least **two distinct shapes coexisting**:
>
> 1. **Prototype-import shape** (e.g. Аптека Апрель): keys
>    `company_overview`, `network_scale`, `geography`, `formats`,
>    `coffee_signals`, `sales_triggers`, `entry_route`, `research_gaps`,
>    `confidence`, `source_id`. This is the verbatim payload from
>    `crm-prototype/data.js` — the 216-lead import (Sprint 1.2)
>    preserved it as-is in the `ai_data` JSON column.
> 2. **ResearchOutput shape** (e.g. Перекрёсток): the canonical
>    `apps/api/app/enrichment/schemas.py:ResearchOutput` shape with
>    `company_profile`, `growth_signals`, `risk_signals`, `fit_score`,
>    `next_steps`, `urgency`, `score_rationale`, etc.
>
> §6's claim that "company_overview / sales_triggers / entry_route /
> research_gaps / source_id have no mapping in CRM" was wrong on a
> technicality — the JSON column **does** carry them today for the bulk
> of legacy rows, but the Pydantic `ResearchOutput` model **ignores**
> them on subsequent enrichment writes. So a new lead card must either:
> (a) read both shapes defensively and merge them, or (b) trigger a
> one-shot migration to normalise legacy rows into the ResearchOutput
> shape, or (c) extend `ResearchOutput` to accept the prototype keys.

### Q3 — coverage stats

```
 total_leads | with_ai_data | with_score | with_fit_score
-------------+--------------+------------+----------------
         216 |          216 |        216 |              4
(1 row)
```

**Key takeaways:**
- **216 leads** in production (matches the 131 v0.5 + 85 v0.6 foodmarkets
  import documented in `00_CURRENT_STATE.md`).
- **All 216 rows have non-empty `ai_data`** — the import preserved the
  prototype enrichment for every row.
- **All 216 rows have `score > 0`** — surprising given §5 inferred
  "likely 0 for most rows". The import populated `score` from the
  prototype's pre-computed value, not from ScoringTab manual entry.
  Section 5's call here was **wrong**. Score column is fully populated.
- **Only 4 rows have `fit_score`** — confirms that the in-product
  Research Agent has only been run on a handful of leads since launch.
  216 − 4 = 212 rows have **legacy prototype enrichment** but **no
  fit_score column populated** — those rows likely have `fit_score`
  inside `ai_data` (prototype shape doesn't have it as a top-level
  number) or not at all.

### Q4 — one full lead row

```
                  id                  | company_name  |               stage_id               | priority | score | fit_score |     segment     |             assigned_to              |          created_at
--------------------------------------+---------------+--------------------------------------+----------+-------+-----------+-----------------+--------------------------------------+-------------------------------
 27d2ba62-5a09-4fe2-a260-8433802bd516 | Аптека Апрель | 5df68d96-4d67-4ccc-93f4-7fc8cfd25c12 | B        |    42 |           | non_food_retail | 75a16d2f-64a4-4c0a-8185-b470d50a9902 | 2026-05-06 14:11:16.983521+00
(1 row)
```

Observations on the first row:
- `priority='B'`, `score=42`, `fit_score=NULL`, `segment='non_food_retail'`.
- `assigned_to` is set (single-workspace post-merge state, see §`00_CURRENT_STATE.md` 2.3 hotfixes).
- `created_at` = `2026-05-06` — matches the import date.

### Q5 — contacts per lead

```
 total_contacts | leads_with_contacts
----------------+---------------------
            659 |                 131
(1 row)
```

- **659 contacts** across **131 leads** → **average ≈ 5.0 contacts per
  lead** for the rows that have any. (Computed: 659 / 131 = 5.03.)
- **85 leads have zero contacts** (216 − 131 = 85). Matches the
  v0.6 foodmarkets import which carried company-level data but no
  per-person rows.
- For the lead card prototype: expect a typical card to surface
  4–6 contacts. The cap at the Multi-stakeholder stage (stage 5,
  `position=5`) makes sense at this cardinality.

---

## Revised conclusions (§5 + §6 corrections from live data)

1. **§5 was wrong on `score`.** Inferred "likely 0 for most rows" from
   grep; live data shows **all 216 rows have `score > 0`**. Source: the
   v0.5/v0.6 prototype import populated `score` from `data.js`'s
   pre-computed value. There is therefore no separate writer in
   `apps/api/` because the writer is the **importer**, not a service.
2. **§6 missed legacy `ai_data` shape.** The prototype's
   `company_overview`, `sales_triggers`, `entry_route`,
   `research_gaps`, `source_id`, `confidence` keys **are** present in
   ~212 of 216 production rows — they live inside `ai_data` as opaque
   JSON, never normalised. The new lead card must handle both shapes.
3. **§5 was right on `fit_score`.** Only 4/216 rows have it — the
   in-product Research Agent has been used sparingly. The Lead Pool
   ordering by `fit_score DESC NULLS LAST` puts 212 rows at the bottom.
4. **§7 still stands.** Per-criterion answers are not persisted —
   only the rolled-up `lead.score` int (which, per #1 above, came
   from the importer, not from ScoringTab).
5. **Contacts coverage:** 131/216 leads have contacts (61%), averaging
   5 contacts each when present. 85 leads (39%) are bare.
