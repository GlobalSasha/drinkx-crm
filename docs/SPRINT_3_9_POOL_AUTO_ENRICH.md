# Sprint 3.9 — Pool Auto-Enrich (lightweight, monthly + on-demand)

**Status:** 📋 SPEC (pre-implementation)
**Date:** 2026-05-20
**Branch:** `sprint/3.9-pool-auto-enrich` (off main)
**Tracking:** `docs/brain/04_NEXT_SPRINT.md`

---

## Goal

Pool leads get a Russian AI Brief automatically — refreshed roughly monthly
per lead, at $0 (a free «lightweight» enrichment using RSS + HH.ru +
web_fetch, no Brave/Tavily), plus on demand. This also fixes the imported
leads whose `ai_data` came pre-filled in **English** from the source dataset
and were never touched by our Russian Research Agent.

Origin: the user found a lead (Hoff) showing an English AI Brief +
«Research gaps». Diagnosis: `import_prototype_data.py` copies the English
`ai_data` straight from `drinkx-client-map-v0.5-linkedin-industry-enriched`;
our Russian `SYNTHESIS_SYSTEM` only runs on a manual «Дополнить». ~236 pool
leads carry this stale English data.

## What already exists (reuse, don't rebuild)

- `apps/api/app/enrichment/orchestrator.py` — the Research Agent pipeline.
  `SYNTHESIS_SYSTEM` already demands Russian output (style rules in place).
- Sources: `sources/brave.py`, `sources/hh.py`, `sources/web_fetch.py`.
- `apps/api/app/enrichment/routers.py` — `POST /leads/{id}/enrichment?mode=full|append`.
  `EnrichmentMode = Literal["full", "append"]` — we ADD `"lightweight"`.
- `apps/api/app/enrichment/models.py` — `EnrichmentRun` table: one row per
  Research Agent invocation, with `status`, `cost_usd`, `provider`, `model`,
  tokens, `sources_used`, `started_at`, `finished_at`. **The selection of
  "stale" leads keys off this table** — pool leads with no `succeeded` run
  in 30 days. Imported leads have ZERO `EnrichmentRun` rows, so they're
  picked up first.
- `apps/api/app/scheduled/jobs.py` — Celery beat registry (the pattern for
  the new `pool_auto_enrich` task).
- `apps/api/app/enrichment/budget.py` — daily Redis spend guard; lightweight
  spend is tiny but still recorded.

## Out of scope (explicit)

- **Tavily** second provider — separate later sprint.
- **LPR finder** (map/crawl/extract + LLM classification) — separate later
  sprint. Expensive (Tavily-heavy), premium-only.
- **Cost counter / admin Расходы page** — Sprint 4.0 (next, separate). Note:
  `EnrichmentRun` already persists per-run cost, so 4.0 mostly needs to
  extend coverage to non-enrichment LLM calls (Blake, inbox classifier,
  daily plan).
- **Telegram t.me/s/ feeds** — fragile HTML scraping; deferred to a
  fast-follow if RSS proves valuable. RSS only in 3.9.
- **News persistence / news feed UI** — RSS items are transient enrichment
  context, not stored.

---

## Design decisions (locked)

1. **«Monthly per lead» = daily beat + 30-day staleness filter.** The beat
   runs daily but only processes pool leads whose last `succeeded`
   `EnrichmentRun` is older than 30 days (or absent). Load spreads evenly
   instead of a monthly spike.
2. **Stale selection = pool leads with no succeeded EnrichmentRun in 30d.**
   `assignment_status = 'pool'` AND `archived_at IS NULL` AND no
   `EnrichmentRun(status='succeeded', finished_at >= now()-30d)`. Imported
   English leads (zero runs) are selected first.
3. **Lightweight mode = RSS + HH + web_fetch.** No Brave, no Tavily. $0 on
   external search APIs. Only the LLM synthesis costs (~$0.0005/lead MiMo
   Flash). The synthesis prompt is unchanged except the `research_gaps` fix.
4. **`research_gaps` added to `SYNTHESIS_SYSTEM`.** Today's bug: the field is
   in the Pydantic `EnrichmentResult` schema but absent from the prompt's
   schema block, so re-enrich would never populate it in Russian. Add it.

---

## Gates

### G1 — RSS feed source

**Files:**
- Create: `apps/api/app/enrichment/sources/rss_feed.py`
- Create: `apps/api/config/news_sources.yaml`
- Modify: `apps/api/pyproject.toml` — add `feedparser>=6.0`

**Behavior:**
- `RssFeedSource.fetch_segment_news(segment, company_name=None, max_items=8)`
  → list of `FeedItem(title, summary, url, published, source_name)`.
- Reads RSS URLs mapped to the lead's `segment` from `news_sources.yaml`.
  Segment values match canonical `lead.segment` (Russian strings) with the
  same alias normalization used in `orchestrator._roles_for_segment`.
- Filters to items newer than 365 days.
- Optional `company_name` → keyword filter; if no company match, fall back
  to top general segment news.
- Per-URL `try/except` — a dead feed logs a warning and is skipped, never
  crashes the enrichment. Cache parsed feeds 2h in Redis (reuse
  `sources/cache.get_redis`).

**Pre-implementation:** validate every RSS URL in the YAML with
`curl -sI <url>` before writing the reader. Keep only feeds that return a
valid 200 + RSS/Atom content-type. Half of any hardcoded RSS list is dead.
Document which survived in the YAML comments.

**`news_sources.yaml` shape:**
```yaml
# segment → RSS feeds. Segment keys are normalized lead.segment values.
# Verified live on 2026-05-20 (see G1 curl pass).
"продуктовый ритейл":
  rss:
    - { url: "<verified-url>", name: "retail.ru" }
"кофейни и кафе":
  rss:
    - { url: "<verified-url>", name: "..." }
# qsr / office inherit retail+horeca via `inherit:` key
"qsr / fast food":
  inherit: ["продуктовый ритейл", "кофейни и кафе"]
```

**Tests** (`apps/api/tests/test_rss_feed.py`, mock httpx):
- `fetch_segment_news` filters out items older than 365 days.
- A dead feed (httpx raises) is skipped, others still return.
- Unknown segment → empty list, no crash.
- `inherit` resolves the parent segments' feeds.

### G2 — `lightweight` enrichment mode

**Files:**
- Modify: `apps/api/app/enrichment/routers.py` — extend
  `EnrichmentMode = Literal["full", "append", "lightweight"]`.
- Modify: `apps/api/app/enrichment/orchestrator.py` — branch on mode.

**Behavior:**
- `lightweight`: gather RSS (`RssFeedSource`) + HH + web_fetch only. Skip
  Brave entirely. Feed all three into the existing synthesis LLM call.
- `full` / `append` unchanged (still use Brave).
- The synthesis prompt gets the RSS items appended to its context block
  (a short «Отраслевые новости» section). Same JSON output schema.

**Tests** (extend `apps/api/tests/test_enrichment_*`, mock sources):
- `lightweight` mode does NOT call Brave (assert brave source not invoked).
- `lightweight` mode DOES call RSS + HH + web_fetch.
- Synthesis still produces a valid `EnrichmentResult`.

### G3 — `research_gaps` in the synthesis prompt

**Files:**
- Modify: `apps/api/app/enrichment/orchestrator.py` — `SYNTHESIS_SYSTEM`.

**Behavior:**
- Add `"research_gaps": str` to the prompt's СХЕМА block (it's already in the
  Pydantic model). Add one rule: «research_gaps — что НЕ удалось подтвердить
  по источникам (контакты ЛПР, число точек, и т.п.). По-русски, кратко. Если
  всё ясно — пустая строка».
- This ensures re-enriched leads get a Russian `research_gaps`, overwriting
  the imported English one (full/lightweight modes replace `ai_data`).

**Test:** assert the prompt string contains `research_gaps` in its schema
block (cheap guard so a future prompt edit doesn't silently drop it again).

### G4 — Celery beat `pool_auto_enrich`

**Files:**
- Modify: `apps/api/app/enrichment/tasks.py` — add the batch task.
- Modify: `apps/api/app/leads/repositories.py` — add
  `get_pool_leads_needing_enrichment(limit)`.
- Modify: `apps/api/app/scheduled/jobs.py` — register the Celery beat entry
  + the sync task wrapper (mirror the existing beat-task pattern).

**Behavior:**
- `get_pool_leads_needing_enrichment(db, limit=20)`:
  ```sql
  SELECT leads.* FROM leads
  WHERE assignment_status = 'pool'
    AND archived_at IS NULL
    AND NOT EXISTS (
      SELECT 1 FROM enrichment_runs er
      WHERE er.lead_id = leads.id
        AND er.status = 'succeeded'
        AND er.finished_at >= now() - interval '30 days'
    )
  ORDER BY leads.created_at ASC
  LIMIT :limit
  ```
- `pool_auto_enrich_batch` Celery task: fetch up to 20 such leads, for each
  enqueue the existing per-lead enrichment in `lightweight` mode with a
  staggered `countdown` (i × 3s throttle so web_fetch isn't hammered).
  Skip a lead if a `running` EnrichmentRun already exists for it.
- Beat schedule in `jobs.py`: `crontab(hour=3, minute=0)` (03:00 UTC = 06:00
  MSK, off-peak). Daily — the 30-day filter makes each lead refresh ~monthly.

**Tests** (`apps/api/tests/test_pool_auto_enrich.py`, mock-stubbed):
- `pool_auto_enrich_batch` enqueues lightweight enrichment for stale leads.
- Leads with a recent succeeded run are NOT re-enqueued.
- Batch respects the limit.
- A lead with a `running` run is skipped.

### G5 — On-demand lightweight trigger + Lead Card button

**Files:**
- Modify: `apps/web/components/lead-card/DealAndAITab.tsx` — the existing
  «Дополнить» control gains a lightweight option (or the AI Brief refresh
  passes `mode=lightweight` when the manager just wants a cheap refresh).
- Backend already supports `?mode=lightweight` after G2 — no new endpoint.

**Behavior:**
- Manager on a lead with stale/English brief can trigger a free lightweight
  re-enrich without spending Brave budget. The existing full enrich stays
  available for deep research.
- UI: keep it minimal — a secondary action «Обновить (быстро, бесплатно)»
  next to the existing «Дополнить». Wire it to `useTriggerEnrichment` with
  `mode: "lightweight"`.

**Verification:** typecheck + lint + pnpm build.

---

## Pre-PR gates

- Backend: `.venv/bin/pytest` on touched test files + `python -m py_compile`
  on touched modules. The full-suite cross-contamination failures (16 on
  main) are pre-existing and out of scope.
- Frontend (G5): `npm run typecheck` + `npm run lint` + `pnpm build`.

---

## Cost

Lightweight = $0 external API. LLM synthesis ~$0.0005/lead (MiMo Flash).
236 pool leads × monthly ≈ $0.12/month. Brave/Tavily untouched.

---

## Smoke checklist (post-deploy)

1. Trigger lightweight on the Hoff lead:
   `POST /leads/<hoff-id>/enrichment?mode=lightweight` → AI Brief regenerates
   in Russian, including a Russian `research_gaps`.
2. `/leads/<hoff-id>` → «Что ещё нужно уточнить» card now Russian.
3. Manually run `pool_auto_enrich_batch` in the worker → logs
   «scheduled N leads»; those leads get EnrichmentRun rows.
4. Re-run the batch → already-enriched leads are NOT re-enqueued (30d filter).
5. RSS source standalone: `RssFeedSource().fetch_segment_news("кофейни и кафе")`
   returns recent items (no crash on any dead feed).

---

## Open questions

None. All design decisions resolved during the 2026-05-20 brainstorm:
monthly = daily-beat + 30d filter; lightweight = RSS+HH+web_fetch; Telegram
deferred; Tavily/LPR + cost counter are separate sprints.
