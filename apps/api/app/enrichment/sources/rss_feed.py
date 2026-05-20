"""RSS feed source — Sprint 3.9 G1.

Reads segment-mapped RSS feeds for free industry-news enrichment context.
feedparser is sync, so we fetch bytes with httpx (async) and hand them to
feedparser.parse(). Per-feed errors are swallowed — a dead feed never
crashes enrichment.
"""
from __future__ import annotations

import calendar
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
        return {_normalize_segment(k): v for k, v in raw.items()}
    except Exception as e:  # noqa: BLE001
        log.warning("rss.config_load_failed", error=str(e)[:200])
        return {}


class RssFeedSource:
    """Fetch recent industry news for a lead's segment from RSS feeds."""

    def __init__(self, config: dict | None = None):
        self._config = (
            {_normalize_segment(k): v for k, v in config.items()}
            if config is not None
            else _load_config()
        )

    def _resolve_feeds(self, segment: str) -> list[dict]:
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
    """feedparser exposes published_parsed (time.struct_time). Convert to
    aware UTC. Returns None if absent / unparseable."""
    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if st is None:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
    except Exception:  # noqa: BLE001
        return None
