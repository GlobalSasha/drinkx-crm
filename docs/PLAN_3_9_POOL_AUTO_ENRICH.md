# Sprint 3.9 — Pool Auto-Enrich · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pool leads get a Russian AI Brief automatically — refreshed ~monthly per lead at $0 via a new lightweight enrichment (RSS + HH + web_fetch, no Brave), plus on-demand. Fixes ~236 imported leads carrying English `ai_data`.

**Architecture:** A new `RssFeedSource` reads segment-mapped RSS feeds (free). The orchestrator gains a `lightweight` mode that runs RSS + HH + web_fetch and skips Brave. A daily Celery beat selects pool leads with no succeeded `EnrichmentRun` in 30 days (imported leads have zero → picked first) and enqueues lightweight enrichment with throttling. The `SYNTHESIS_SYSTEM` prompt gains the missing `research_gaps` field so re-enriched leads get a Russian gaps note.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy async, Celery beat/worker, feedparser (new dep), httpx, pyyaml, pytest with mock-stubbed sqlalchemy. Frontend (G5 only): Next.js 15, React, TanStack Query.

**Spec:** `docs/SPRINT_3_9_POOL_AUTO_ENRICH.md`

**Branch:** `sprint/3.9-pool-auto-enrich` (off main).

---

## File map

**Backend (`apps/api/`):**
- Modify `pyproject.toml` — add `feedparser>=6.0`.
- Create `config/news_sources.yaml` — segment → verified RSS feeds.
- Create `app/enrichment/sources/rss_feed.py` — `RssFeedSource`, `FeedItem`.
- Modify `app/enrichment/orchestrator.py` — `lightweight` branch + RSS block in synthesis + `research_gaps` in `SYNTHESIS_SYSTEM`.
- Modify `app/enrichment/routers.py` — `EnrichmentMode` adds `"lightweight"`.
- Modify `app/leads/repositories.py` — `get_pool_leads_needing_enrichment`.
- Modify `app/enrichment/tasks.py` — `pool_auto_enrich_batch` async core.
- Modify `app/scheduled/jobs.py` — Celery task wrapper + beat schedule entry.

**Backend tests:**
- Create `tests/test_rss_feed.py`.
- Create `tests/test_pool_auto_enrich.py`.
- Extend an enrichment test for `research_gaps` prompt presence.

**Frontend (`apps/web/`, G5):**
- Modify `lib/hooks/use-enrichment.ts` — allow `mode` arg on the trigger hook.
- Modify `components/lead-card/DealAndAITab.tsx` — «Обновить (быстро)» button → lightweight.

---

## Task 1 — feedparser dependency + RSS feed source

**Files:**
- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/config/news_sources.yaml`
- Create: `apps/api/app/enrichment/sources/rss_feed.py`
- Create: `apps/api/tests/test_rss_feed.py`

### Step 1.1 — Validate RSS URLs FIRST (no code yet)

- [ ] Run a connectivity check on candidate feeds, keep only live ones:

```bash
for u in \
  "https://www.retail.ru/rss/all.xml" \
  "https://www.pitportal.ru/feed" \
  "https://restoranoved.ru/feed" \
  "https://www.cofer.ru/feed" \
  "https://neftegaz.ru/rss/" ; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -L --max-time 12 "$u")
  echo "$code  $u"
done
```

- [ ] For each URL returning 200, confirm it's real RSS/Atom (not an HTML 200):
  `curl -s -L --max-time 12 "<url>" | head -c 300` — expect `<rss` or `<feed`.
- [ ] Record the survivors. Only verified-live feeds go into the YAML. If a
      segment ends up with zero live feeds, that's fine — the source returns
      an empty list for it (the synthesis still runs on HH + web_fetch).

### Step 1.2 — Add the dependency

- [ ] Open `apps/api/pyproject.toml`. In the `dependencies = [` list, add:

```python
    "feedparser>=6.0",
```

- [ ] Install into the venv: `cd apps/api && .venv/bin/pip install "feedparser>=6.0"`

### Step 1.3 — Write `news_sources.yaml`

- [ ] Create `apps/api/config/news_sources.yaml` using ONLY the URLs that
      passed Step 1.1. Keys are normalized `lead.segment` values. Example
      shape (replace with verified URLs):

```yaml
# segment → RSS feeds. Keys match normalized lead.segment.
# Verified live on 2026-05-20 (see plan Task 1 Step 1.1).
"продуктовый ритейл":
  rss:
    - { url: "https://www.retail.ru/rss/all.xml", name: "retail.ru" }
"кофейни и кафе":
  rss:
    - { url: "https://restoranoved.ru/feed", name: "Ресторановед" }
"horeca":
  rss:
    - { url: "https://www.pitportal.ru/feed", name: "ПитПортал" }
"азс":
  rss:
    - { url: "https://neftegaz.ru/rss/", name: "Нефтегаз" }
# Segments without dedicated feeds inherit others.
"qsr / fast food":
  inherit: ["продуктовый ритейл", "horeca"]
"непродуктовый ритейл":
  inherit: ["продуктовый ритейл"]
```

> If a candidate URL failed Step 1.1, drop that line. Don't ship dead feeds.

### Step 1.4 — Write the failing test

- [ ] Create `apps/api/tests/test_rss_feed.py`:

```python
"""Sprint 3.9 G1 — RSS feed source."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def _rss_xml(items: list[tuple[str, str, str]]) -> str:
    """items = list of (title, link, pubdate_rfc822)."""
    entries = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        f"<description>desc {t}</description><pubDate>{d}</pubDate></item>"
        for (t, l, d) in items
    )
    return f"<rss><channel>{entries}</channel></rss>"


@pytest.mark.asyncio
async def test_fetch_filters_items_older_than_365_days():
    from app.enrichment.sources.rss_feed import RssFeedSource

    fresh = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    old = (datetime.now(timezone.utc) - timedelta(days=500)).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    xml = _rss_xml([("Fresh news", "https://x/1", fresh),
                    ("Old news", "https://x/2", old)])

    src = RssFeedSource(config={"retail": {"rss": [{"url": "u", "name": "n"}]}})
    with patch.object(src, "_http_get", new=AsyncMock(return_value=xml)):
        with patch.object(src, "_cache_get", new=AsyncMock(return_value=None)):
            with patch.object(src, "_cache_set", new=AsyncMock()):
                items = await src.fetch_segment_news("retail")

    titles = [i.title for i in items]
    assert "Fresh news" in titles
    assert "Old news" not in titles


@pytest.mark.asyncio
async def test_dead_feed_is_skipped_not_fatal():
    from app.enrichment.sources.rss_feed import RssFeedSource

    src = RssFeedSource(config={
        "retail": {"rss": [
            {"url": "dead", "name": "dead"},
            {"url": "live", "name": "live"},
        ]}
    })
    fresh = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    live_xml = _rss_xml([("Live item", "https://x/1", fresh)])

    async def _get(url):
        if url == "dead":
            raise RuntimeError("boom")
        return live_xml

    with patch.object(src, "_http_get", new=_get):
        with patch.object(src, "_cache_get", new=AsyncMock(return_value=None)):
            with patch.object(src, "_cache_set", new=AsyncMock()):
                items = await src.fetch_segment_news("retail")

    assert [i.title for i in items] == ["Live item"]


@pytest.mark.asyncio
async def test_unknown_segment_returns_empty():
    from app.enrichment.sources.rss_feed import RssFeedSource

    src = RssFeedSource(config={"retail": {"rss": []}})
    items = await src.fetch_segment_news("nonexistent-segment")
    assert items == []


@pytest.mark.asyncio
async def test_inherit_resolves_parent_feeds():
    from app.enrichment.sources.rss_feed import RssFeedSource

    src = RssFeedSource(config={
        "retail": {"rss": [{"url": "r", "name": "retail"}]},
        "qsr": {"inherit": ["retail"]},
    })
    fresh = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = _rss_xml([("Retail item", "https://x/1", fresh)])

    with patch.object(src, "_http_get", new=AsyncMock(return_value=xml)):
        with patch.object(src, "_cache_get", new=AsyncMock(return_value=None)):
            with patch.object(src, "_cache_set", new=AsyncMock()):
                items = await src.fetch_segment_news("qsr")

    assert [i.title for i in items] == ["Retail item"]
```

### Step 1.5 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_rss_feed.py -v`
- [ ] Expected: `ModuleNotFoundError: No module named 'app.enrichment.sources.rss_feed'`.

### Step 1.6 — Implement `rss_feed.py`

- [ ] Create `apps/api/app/enrichment/sources/rss_feed.py`:

```python
"""RSS feed source — Sprint 3.9 G1.

Reads segment-mapped RSS feeds for free industry-news enrichment context.
feedparser is sync, so we fetch bytes with httpx (async) and hand them to
feedparser.parse(). Per-feed errors are swallowed — a dead feed never
crashes enrichment.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import structlog
import yaml

log = structlog.get_logger()

CUTOFF_DAYS = 365
_CACHE_TTL_SECONDS = 2 * 60 * 60  # 2h
_HTTP_TIMEOUT = 12.0
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "news_sources.yaml"


@dataclass
class FeedItem:
    title: str
    summary: str
    url: str
    published: datetime
    source_name: str


def _normalize_segment(segment: str) -> str:
    return (segment or "").strip().lower()


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        # Normalize keys to lowercase for case-insensitive lookup.
        return {_normalize_segment(k): v for k, v in raw.items()}
    except Exception as e:  # noqa: BLE001
        log.warning("rss.config_load_failed", error=str(e)[:200])
        return {}


class RssFeedSource:
    """Fetch recent industry news for a lead's segment from RSS feeds."""

    def __init__(self, config: dict | None = None):
        # config injectable for tests; otherwise load the YAML once.
        self._config = (
            {_normalize_segment(k): v for k, v in config.items()}
            if config is not None
            else _load_config()
        )

    def _resolve_feeds(self, segment: str) -> list[dict]:
        """Return the rss feed list for a segment, expanding `inherit`."""
        key = _normalize_segment(segment)
        node = self._config.get(key)
        if not node:
            return []
        if "inherit" in node:
            feeds: list[dict] = []
            for parent in node["inherit"]:
                feeds.extend(self._resolve_feeds(parent))
            return feeds
        return list(node.get("rss", []))

    async def fetch_segment_news(
        self,
        segment: str,
        company_name: str | None = None,
        max_items: int = 8,
    ) -> list[FeedItem]:
        feeds = self._resolve_feeds(segment)
        if not feeds:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)
        collected: list[FeedItem] = []

        for feed in feeds:
            url = feed.get("url")
            name = feed.get("name", url or "rss")
            if not url:
                continue
            try:
                items = await self._fetch_one(url, name, cutoff)
                collected.extend(items)
            except Exception as e:  # noqa: BLE001
                log.warning("rss.feed_failed", url=url, error=str(e)[:200])
                continue

        if company_name:
            kw = company_name.strip().lower()
            relevant = [
                i for i in collected
                if kw in i.title.lower() or kw in i.summary.lower()
            ]
            if relevant:
                collected = relevant

        collected.sort(key=lambda x: x.published, reverse=True)
        return collected[:max_items]

    async def _fetch_one(
        self, url: str, name: str, cutoff: datetime
    ) -> list[FeedItem]:
        cached = await self._cache_get(url)
        raw = cached if cached is not None else await self._http_get(url)
        if cached is None:
            await self._cache_set(url, raw)

        parsed = feedparser.parse(raw)
        out: list[FeedItem] = []
        for entry in parsed.entries:
            published = _entry_datetime(entry)
            if published is None or published < cutoff:
                continue
            out.append(
                FeedItem(
                    title=getattr(entry, "title", "").strip(),
                    summary=(getattr(entry, "summary", "") or "")[:300].strip(),
                    url=getattr(entry, "link", "").strip(),
                    published=published,
                    source_name=name,
                )
            )
        return out

    async def _http_get(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    async def _cache_get(self, url: str) -> str | None:
        try:
            from app.enrichment.sources.cache import get_redis

            client = get_redis()
            return await client.get(f"rss:{url}")
        except Exception:  # noqa: BLE001
            return None

    async def _cache_set(self, url: str, raw: str) -> None:
        try:
            from app.enrichment.sources.cache import get_redis

            client = get_redis()
            await client.set(f"rss:{url}", raw, ex=_CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            pass


def _entry_datetime(entry) -> datetime | None:
    """feedparser exposes published_parsed (time.struct_time) — convert to
    aware UTC datetime. Returns None if absent / unparseable."""
    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if st is None:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(st), tz=timezone.utc)
    except Exception:  # noqa: BLE001
        return None
```

Note: the cache returns the raw feed bytes/text as a string; `feedparser.parse`
accepts a string. The redis client in this repo decodes responses to str
(verify; if it returns bytes, `feedparser.parse` accepts bytes too — no change
needed).

### Step 1.7 — Run, confirm pass

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_rss_feed.py -v`
- [ ] Expected: 4 tests PASS.

### Step 1.8 — Commit

```bash
git add apps/api/pyproject.toml apps/api/config/news_sources.yaml \
        apps/api/app/enrichment/sources/rss_feed.py \
        apps/api/tests/test_rss_feed.py
git commit -m "feat(enrichment): G1 — RSS feed source + verified news_sources.yaml"
```

---

## Task 2 — `lightweight` enrichment mode

**Files:**
- Modify: `apps/api/app/enrichment/routers.py` (`EnrichmentMode` literal)
- Modify: `apps/api/app/enrichment/orchestrator.py` (mode branch + RSS block)

### Step 2.1 — Extend the mode literal

- [ ] Open `apps/api/app/enrichment/routers.py`. Change:

```python
EnrichmentMode = Literal["full", "append"]
```

to:

```python
EnrichmentMode = Literal["full", "append", "lightweight"]
```

- [ ] Update the `Query(...)` description on the trigger endpoint to mention
      lightweight (free, no Brave). Find the `mode: EnrichmentMode = Query(`
      block and extend its description string.

### Step 2.2 — Add RSS block to USER_TMPL

- [ ] Open `apps/api/app/enrichment/orchestrator.py`. Find `USER_TMPL`
      (around line 210). It has `{brave_block}`, `{hh_block}`, `{web_block}`.
      Add an RSS section. Insert after the web block placeholder:

```python
# In USER_TMPL string, append a new labeled section:
# Отраслевые новости (RSS):
# {rss_block}
```

  Add `{rss_block}` to the template and a `_format_rss_block(items)` helper
  near `_format_web_block`:

```python
def _format_rss_block(items: list) -> str:
    """Render RSS FeedItems for the synthesis prompt. Empty → marker."""
    if not items:
        return "(нет свежих отраслевых новостей)"
    lines = []
    for it in items[:8]:
        date = it.published.strftime("%Y-%m-%d")
        lines.append(f"- [{date}] {it.title} ({it.source_name})")
    return "\n".join(lines)
```

### Step 2.3 — Branch the fetch on mode

- [ ] In `run_enrichment` (around line 640-657), make Brave conditional and
      always fetch RSS. Replace the query-build + fetch-tasks block:

```python
        # --- Step 1: Build queries ---
        hh_query = lead.company_name or ""
        use_brave = mode != "lightweight"
        brave_queries = _build_queries(lead) if use_brave else []

        # --- Step 2: Parallel fetch ---
        brave_source = BraveSearch()
        hh_source = HHRu()
        web_source = WebFetch()

        from app.enrichment.sources.rss_feed import RssFeedSource
        rss_source = RssFeedSource()

        fetch_tasks: list[Any] = [
            brave_source.fetch(q, use_cache=True) for q in brave_queries
        ]
        fetch_tasks.append(hh_source.fetch(hh_query, use_cache=True))

        has_website = bool(lead.website and lead.website.strip())
        if has_website:
            fetch_tasks.append(web_source.fetch(lead.website, use_cache=True))  # type: ignore[arg-type]

        # RSS is fetched separately (different return type) — run it
        # concurrently but handle its result independently.
        rss_items = await rss_source.fetch_segment_news(
            segment=lead.segment or "",
            company_name=lead.company_name,
            max_items=8,
        )

        raw_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
```

- [ ] The result-separation loop below uses `n_brave = len(brave_queries)`.
      In lightweight mode `n_brave == 0`, so index 0 is HH, index 1 (if
      present) is web — the existing `if i < n_brave / elif i == n_brave /
      else` logic still works because `n_brave == 0` makes HH land at
      `i == n_brave`. Verify by reading; no change needed.

### Step 2.4 — Pass rss_block into the prompt

- [ ] In the `USER_TMPL.format(...)` call (around line 689), add:

```python
            rss_block=_format_rss_block(rss_items),
```

- [ ] In `_collect_sources_used` (around line 500), add an `rss` entry when
      `rss_items` is non-empty. Simplest: after the existing call, append:

```python
        if rss_items and "rss" not in sources_used:
            sources_used.append("rss")
```

  (Place this right after `sources_used = _collect_sources_used(...)`.)

### Step 2.5 — Write the mode test

- [ ] Create / extend `apps/api/tests/test_lightweight_mode.py`:

```python
"""Sprint 3.9 G2 — lightweight enrichment mode skips Brave."""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    class _C:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _C()
    _sa_orm.defer = _C()


def test_format_rss_block_empty_and_populated():
    from app.enrichment.orchestrator import _format_rss_block
    from app.enrichment.sources.rss_feed import FeedItem
    from datetime import datetime, timezone

    assert "нет свежих" in _format_rss_block([])

    item = FeedItem(
        title="Сеть открыла 5 точек",
        summary="...",
        url="https://x/1",
        published=datetime(2026, 5, 1, tzinfo=timezone.utc),
        source_name="retail.ru",
    )
    block = _format_rss_block([item])
    assert "Сеть открыла 5 точек" in block
    assert "2026-05-01" in block
    assert "retail.ru" in block
```

> A full integration test of `run_enrichment` lightweight mode requires a real
> DB + mocked sources and doesn't fit the mock-stub harness cleanly. The
> `_format_rss_block` unit test + manual smoke (Task 7) cover the behavior;
> the brave-skip logic is a one-line `use_brave = mode != "lightweight"`
> guard that's verified by reading.

### Step 2.6 — Run + commit

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_lightweight_mode.py tests/test_rss_feed.py -v` → all pass.
- [ ] `python -m py_compile app/enrichment/orchestrator.py app/enrichment/routers.py`

```bash
git add apps/api/app/enrichment/orchestrator.py apps/api/app/enrichment/routers.py \
        apps/api/tests/test_lightweight_mode.py
git commit -m "feat(enrichment): G2 — lightweight mode (RSS+HH+web_fetch, no Brave)"
```

---

## Task 3 — `research_gaps` in SYNTHESIS_SYSTEM

**Files:**
- Modify: `apps/api/app/enrichment/orchestrator.py` (`SYNTHESIS_SYSTEM`)
- Modify: `apps/api/tests/test_lightweight_mode.py` (add a prompt guard)

### Step 3.1 — Write the failing guard test

- [ ] Append to `apps/api/tests/test_lightweight_mode.py`:

```python
def test_synthesis_prompt_includes_research_gaps():
    """research_gaps is in the Pydantic schema but was missing from the
    prompt's СХЕМА block — re-enrich never produced it in Russian. Guard
    so a future prompt edit doesn't silently drop it again."""
    from app.enrichment.orchestrator import SYNTHESIS_SYSTEM

    assert "research_gaps" in SYNTHESIS_SYSTEM
```

### Step 3.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_lightweight_mode.py::test_synthesis_prompt_includes_research_gaps -v`
- [ ] Expected: FAIL (assert `"research_gaps" in SYNTHESIS_SYSTEM` is False).

### Step 3.3 — Add the field to the prompt

- [ ] Open `apps/api/app/enrichment/orchestrator.py`. In `SYNTHESIS_SYSTEM`,
      add `"research_gaps": str` to the СХЕМА JSON block (after `"notes": str`):

```python
  "notes": str,
  "research_gaps": str
}"""
```

- [ ] Add a rule in the ПРАВИЛА ВЫВОДА section:

```
9. research_gaps — что НЕ удалось подтвердить по источникам (контакты ЛПР,
   точное число точек, модель франшизы и т.п.). По-русски, кратко, одним
   абзацем. Если всё подтверждено — пустая строка "".
```

### Step 3.4 — Run, confirm pass + commit

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_lightweight_mode.py -v` → all pass.

```bash
git add apps/api/app/enrichment/orchestrator.py apps/api/tests/test_lightweight_mode.py
git commit -m "fix(enrichment): G3 — add research_gaps to SYNTHESIS_SYSTEM prompt"
```

---

## Task 4 — `get_pool_leads_needing_enrichment` repo query

**Files:**
- Modify: `apps/api/app/leads/repositories.py`
- Modify: `apps/api/tests/test_pool_auto_enrich.py` (created here)

### Step 4.1 — Write the failing test

- [ ] Create `apps/api/tests/test_pool_auto_enrich.py`:

```python
"""Sprint 3.9 G4 — pool auto-enrich selection + batch."""
from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    class _C:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _C()
    _sa_orm.defer = _C()


@pytest.mark.asyncio
async def test_get_pool_leads_needing_enrichment_returns_rows():
    from app.leads import repositories as repo

    lead_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=lambda: MagicMock(all=lambda: [MagicMock(id=lead_id)])
        )
    )

    rows = await repo.get_pool_leads_needing_enrichment(db, limit=20)

    assert len(rows) == 1
    assert rows[0].id == lead_id
    db.execute.assert_awaited_once()
```

### Step 4.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_pool_auto_enrich.py::test_get_pool_leads_needing_enrichment_returns_rows -v`
- [ ] Expected: `AttributeError: module 'app.leads.repositories' has no attribute 'get_pool_leads_needing_enrichment'`.

### Step 4.3 — Implement the query

- [ ] Open `apps/api/app/leads/repositories.py`. Add:

```python
async def get_pool_leads_needing_enrichment(
    db: AsyncSession, limit: int = 20
) -> list[Lead]:
    """Sprint 3.9 G4 — pool leads with no succeeded EnrichmentRun in the
    last 30 days. Imported leads (zero runs) are selected first. Drives
    the monthly-per-lead auto-enrich beat."""
    import datetime as _dt

    from app.enrichment.models import EnrichmentRun

    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)
    recent_run_exists = (
        select(EnrichmentRun.id)
        .where(
            EnrichmentRun.lead_id == Lead.id,
            EnrichmentRun.status == "succeeded",
            EnrichmentRun.finished_at >= cutoff,
        )
        .exists()
    )
    stmt = (
        select(Lead)
        .where(
            Lead.assignment_status == "pool",
            Lead.archived_at.is_(None),
            ~recent_run_exists,
        )
        .order_by(Lead.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
```

- [ ] Verify `Lead.archived_at` exists: `grep -n "archived_at" apps/api/app/leads/models.py`. If the column has a different name, adapt.

### Step 4.4 — Run, confirm pass + commit

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_pool_auto_enrich.py -v` → pass.

```bash
git add apps/api/app/leads/repositories.py apps/api/tests/test_pool_auto_enrich.py
git commit -m "feat(leads): G4 — get_pool_leads_needing_enrichment query"
```

---

## Task 5 — `pool_auto_enrich_batch` Celery task + beat

**Files:**
- Modify: `apps/api/app/enrichment/tasks.py` (async core)
- Modify: `apps/api/app/scheduled/jobs.py` (sync wrapper + beat schedule)
- Modify: `apps/api/tests/test_pool_auto_enrich.py`

### Step 5.1 — Write the failing test

- [ ] Append to `apps/api/tests/test_pool_auto_enrich.py`:

```python
@pytest.mark.asyncio
async def test_pool_auto_enrich_batch_enqueues_lightweight():
    """Stale pool leads get a lightweight enrichment enqueued, staggered."""
    from app.enrichment import tasks as t

    lead_ids = [uuid.uuid4(), uuid.uuid4()]
    fake_leads = [MagicMock(id=lid) for lid in lead_ids]

    with patch.object(
        t, "get_pool_leads_needing_enrichment",
        new=AsyncMock(return_value=fake_leads),
    ):
        with patch.object(t, "_enqueue_lightweight_enrich", new=AsyncMock()) as enq:
            with patch.object(t, "_running_run_exists", new=AsyncMock(return_value=False)):
                out = await t._run_pool_auto_enrich_batch(limit=20)

    assert enq.await_count == 2
    assert out["scheduled"] == 2


@pytest.mark.asyncio
async def test_pool_auto_enrich_skips_lead_with_running_run():
    from app.enrichment import tasks as t

    fake_leads = [MagicMock(id=uuid.uuid4())]
    with patch.object(
        t, "get_pool_leads_needing_enrichment",
        new=AsyncMock(return_value=fake_leads),
    ):
        with patch.object(t, "_enqueue_lightweight_enrich", new=AsyncMock()) as enq:
            with patch.object(t, "_running_run_exists", new=AsyncMock(return_value=True)):
                out = await t._run_pool_auto_enrich_batch(limit=20)

    enq.assert_not_awaited()
    assert out["scheduled"] == 0
```

### Step 5.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_pool_auto_enrich.py -v -k batch`
- [ ] Expected: `AttributeError` — `_run_pool_auto_enrich_batch` doesn't exist.

### Step 5.3 — Implement the async core in `tasks.py`

- [ ] Open `apps/api/app/enrichment/tasks.py`. Read the existing per-lead
      enrichment enqueue pattern (how `run_enrichment` is invoked — likely a
      `trigger_enrichment` helper that creates an EnrichmentRun row then
      dispatches `_bg_run` / a Celery task). Add:

```python
async def _running_run_exists(db, lead_id) -> bool:
    from sqlalchemy import select
    from app.enrichment.models import EnrichmentRun

    res = await db.execute(
        select(EnrichmentRun.id)
        .where(EnrichmentRun.lead_id == lead_id, EnrichmentRun.status == "running")
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def _enqueue_lightweight_enrich(db, lead_id, *, countdown: int) -> None:
    """Create an EnrichmentRun row + dispatch the lightweight enrichment
    via the existing per-lead path. Mirrors the manual-trigger flow but
    with mode='lightweight' and no user_id (system-initiated)."""
    from app.enrichment import services as enrich_services
    from app.scheduled.celery_app import celery_app

    run = await enrich_services.create_run(db, lead_id=lead_id, user_id=None)
    await db.commit()
    celery_app.send_task(
        "app.scheduled.jobs.run_enrichment_task",
        args=[str(run.id), "lightweight"],
        countdown=countdown,
    )


async def _run_pool_auto_enrich_batch(limit: int = 20) -> dict:
    """Select stale pool leads and enqueue lightweight enrichment for each,
    staggered 3s apart. Skips leads already running."""
    from app.leads.repositories import get_pool_leads_needing_enrichment
    # NOTE: imported at module top in real code so tests can patch
    # `tasks.get_pool_leads_needing_enrichment` — see import note below.

    engine, factory = _build_task_engine_and_factory()
    scheduled = 0
    try:
        async with factory() as db:
            leads = await get_pool_leads_needing_enrichment(db, limit=limit)
            for i, lead in enumerate(leads):
                if await _running_run_exists(db, lead.id):
                    continue
                await _enqueue_lightweight_enrich(db, lead.id, countdown=i * 3)
                scheduled += 1
    finally:
        await engine.dispose()

    log.info("pool_auto_enrich.scheduled", count=scheduled)
    return {"job": "pool_auto_enrich_batch", "scheduled": scheduled}
```

- [ ] **Import note for testability:** at the top of `tasks.py`, add
      `from app.leads.repositories import get_pool_leads_needing_enrichment`
      (module-level) so the test's `patch.object(t, "get_pool_leads_needing_enrichment")`
      works. Remove the inner import in `_run_pool_auto_enrich_batch`.
- [ ] Verify `enrich_services.create_run` signature exists with
      `(db, lead_id, user_id)` — read `app/enrichment/services.py`. Adapt the
      call to the real signature (it may be `create_run(db, lead_id=..., user_id=...)`).
- [ ] Verify `_build_task_engine_and_factory` is importable here — it lives in
      `app/scheduled/jobs.py`. Either import it or replicate the small helper.
      Cleaner: keep `_run_pool_auto_enrich_batch` in `tasks.py` but have it
      receive a session factory, OR move the engine creation to jobs.py and
      pass `db` in. Pick whichever matches the existing task pattern after
      reading `jobs.py`. (If `jobs.py` owns engine creation for all Celery
      tasks, define `_run_pool_auto_enrich_batch` to build its own engine via
      the same helper imported from jobs.)

### Step 5.4 — Register the Celery task + beat in `jobs.py`

- [ ] Open `apps/api/app/scheduled/jobs.py`. Add a sync task wrapper:

```python
@celery_app.task(name="app.scheduled.jobs.pool_auto_enrich_batch")
def pool_auto_enrich_batch() -> dict:
    """Sprint 3.9 — daily beat. Lightweight-enrich pool leads stale >30 days."""
    from app.enrichment.tasks import _run_pool_auto_enrich_batch

    return asyncio.run(_run_pool_auto_enrich_batch(limit=20))
```

- [ ] Add a `run_enrichment_task` sync wrapper IF one doesn't already exist
      (check: `grep -n "run_enrichment" app/scheduled/jobs.py`). The manual
      trigger uses `_bg_run` via FastAPI BackgroundTasks, not Celery, so a
      Celery entry-point for enrichment may be new. If absent, add:

```python
@celery_app.task(name="app.scheduled.jobs.run_enrichment_task")
def run_enrichment_task(run_id: str, mode: str = "full") -> dict:
    """Celery entry-point for enrichment (used by pool_auto_enrich_batch)."""
    from uuid import UUID
    from app.enrichment.orchestrator import run_enrichment

    async def _core():
        engine, factory = _build_task_engine_and_factory()
        try:
            async with factory() as db:
                await run_enrichment(db=db, run_id=UUID(run_id), mode=mode)
        finally:
            await engine.dispose()
        return {"job": "run_enrichment_task", "run_id": run_id, "mode": mode}

    return asyncio.run(_core())
```

- [ ] Register the beat schedule. Find the `beat_schedule` / `celery_app.conf.beat_schedule`
      registry (or the crontab list) and add:

```python
    "pool-auto-enrich": {
        "task": "app.scheduled.jobs.pool_auto_enrich_batch",
        "schedule": crontab(hour=3, minute=0),  # 03:00 UTC = 06:00 MSK
    },
```

  Match the exact registration style already used for other beat tasks
  (`gmail_incremental_sync`, `lead_agent_scan_silence`, etc.).

### Step 5.5 — Run + commit

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_pool_auto_enrich.py -v` → all pass.
- [ ] `python -m py_compile app/enrichment/tasks.py app/scheduled/jobs.py`

```bash
git add apps/api/app/enrichment/tasks.py apps/api/app/scheduled/jobs.py \
        apps/api/tests/test_pool_auto_enrich.py
git commit -m "feat(enrichment): G4 — pool_auto_enrich_batch Celery task + daily beat"
```

---

## Task 6 — On-demand lightweight trigger + Lead Card button

**Files:**
- Modify: `apps/web/lib/hooks/use-enrichment.ts`
- Modify: `apps/web/components/lead-card/DealAndAITab.tsx`

### Step 6.1 — Allow `mode` on the trigger hook

- [ ] Open `apps/web/lib/hooks/use-enrichment.ts`. Find `useTriggerEnrichment`.
      It currently posts to `/leads/{id}/enrichment?mode=...`. Confirm it
      accepts a `mode` argument; if it hardcodes `full`/`append`, extend the
      mutation input type to accept `"lightweight"`. Read the hook first; the
      Sprint 3.6/earlier code likely already passes `mode` as the mutation
      variable (`trigger.mutate("full" | "append")`). Add `"lightweight"` to
      the union.

### Step 6.2 — Add the button

- [ ] Open `apps/web/components/lead-card/DealAndAITab.tsx`. Find the AI Brief
      card header where «Дополнить» (append) lives (around the `handleRun`
      function from earlier sprints). Add a secondary button:

```tsx
<button
  type="button"
  onClick={() => handleRun("lightweight")}
  disabled={isRunning}
  className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-50 transition-opacity`}
  title="Бесплатное обновление: новости отрасли + сайт + вакансии, без Brave"
>
  Обновить (быстро)
</button>
```

- [ ] `handleRun` currently accepts `"full" | "append"`. Widen its parameter
      type to include `"lightweight"` and pass it straight to
      `trigger.mutate(mode)`. The toast on success can stay generic
      («AI Бриф в очереди — обычно 5–10 сек»).

### Step 6.3 — Verify

- [ ] Run: `cd apps/web && npm run typecheck && npm run lint && pnpm build`
- [ ] Expected: typecheck clean, lint baseline (21 warnings), build green.

### Step 6.4 — Commit

```bash
git add apps/web/lib/hooks/use-enrichment.ts apps/web/components/lead-card/DealAndAITab.tsx
git commit -m "feat(lead-card): G5 — on-demand lightweight enrich button"
```

---

## Task 7 — Smoke verification + PR

**Files:** none (manual) + sprint spec checklist tick.

### Step 7.1 — Smoke each path (post-deploy or local)

- [ ] RSS source standalone (no LLM):
  ```bash
  cd apps/api && .venv/bin/python -c "
  import asyncio
  from app.enrichment.sources.rss_feed import RssFeedSource
  items = asyncio.run(RssFeedSource().fetch_segment_news('кофейни и кафе', max_items=5))
  print([(i.title, i.source_name) for i in items])
  "
  ```
  Expect: a list of recent items (or empty if no live feeds for that segment), no crash.
- [ ] Lightweight enrich on the Hoff lead:
  `POST /leads/<hoff-id>/enrichment?mode=lightweight` → 202. Wait ~10s,
  reopen the lead → AI Brief in Russian, «Что ещё нужно уточнить» in Russian.
- [ ] Manually run the batch in the worker container:
  `celery -A app.scheduled.celery_app call app.scheduled.jobs.pool_auto_enrich_batch`
  → worker logs «pool_auto_enrich.scheduled count=N».
- [ ] Re-run the batch → already-enriched leads NOT re-enqueued (30d filter).
- [ ] Lead Card → «Обновить (быстро)» button triggers lightweight, no Brave spend.

### Step 7.2 — Tick the spec smoke checklist

- [ ] Update `docs/SPRINT_3_9_POOL_AUTO_ENRICH.md` smoke checklist.

### Step 7.3 — Push + PR

```bash
git push -u origin sprint/3.9-pool-auto-enrich
gh pr create --title "Sprint 3.9 — Pool Auto-Enrich (lightweight, monthly + on-demand)" --body "..."
```

PR body: gate-by-gate recap + test plan (mirror Sprint 3.6/3.7 format).
Reference `docs/SPRINT_3_9_POOL_AUTO_ENRICH.md`.

---

## Self-review notes (2026-05-20)

- **Spec coverage:** G1→Task1, G2→Task2, G3→Task3, G4→Tasks4+5, G5→Task6,
  smoke→Task7. All gates mapped.
- **Placeholder scan:** `news_sources.yaml` URLs are validated in Task 1
  Step 1.1 before use (not hidden TBDs — an explicit validation step). PR
  body «...» filled at Task 7. No code-step placeholders.
- **Type consistency:** `FeedItem` (title/summary/url/published/source_name)
  consistent across rss_feed.py + tests + `_format_rss_block`. `mode`
  literal `"lightweight"` consistent across routers, orchestrator,
  tasks, frontend. `get_pool_leads_needing_enrichment(db, limit)` signature
  consistent between repo, task, and tests. `_run_pool_auto_enrich_batch`,
  `_enqueue_lightweight_enrich`, `_running_run_exists` names consistent
  between Task 5 impl and tests.
- **Risk flagged for implementer:** Task 5 has the most integration
  uncertainty (Celery entry-point for enrichment may be new; `create_run`
  signature; engine-factory location). The task tells the implementer to
  read `jobs.py` + `services.py` first and adapt. If blocked, that's the
  task to escalate.
