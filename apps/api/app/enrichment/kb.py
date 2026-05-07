"""Knowledge base loader — reads markdown files with YAML frontmatter.

Static content; loaded once per process via lru_cache. Re-deploy to refresh.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

import structlog
import yaml

log = structlog.get_logger()

# apps/api/app/enrichment/kb.py → ../../../knowledge/drinkx
_KB_PATH = pathlib.Path(__file__).resolve().parents[2] / "knowledge" / "drinkx"

# Cap how much KB context we inject — keeps the synthesis prompt sane
_MAX_TOTAL_CHARS = 6000
_PER_ENTRY_CHARS = 1800
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass(frozen=True)
class KBEntry:
    slug: str
    title: str
    segments: tuple[str, ...]
    priority: int
    always_on: bool
    body: str


def _parse_one(path: pathlib.Path) -> KBEntry | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("kb.read_failed", path=str(path), error=str(e))
        return None

    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        try:
            meta = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError as e:
            log.warning("kb.frontmatter_parse_failed", path=str(path), error=str(e))
            meta = {}
        body = text[fm_match.end():]
    else:
        meta, body = {}, text

    slug = str(meta.get("slug") or path.stem)
    title = str(meta.get("title") or slug)
    raw_segments = meta.get("segments") or []
    if isinstance(raw_segments, str):
        raw_segments = [raw_segments]
    segments = tuple(str(s).strip() for s in raw_segments if str(s).strip())
    priority = int(meta.get("priority") or 0)
    always_on = bool(meta.get("always_on"))

    return KBEntry(
        slug=slug,
        title=title,
        segments=segments,
        priority=priority,
        always_on=always_on,
        body=body.strip(),
    )


@lru_cache(maxsize=1)
def load_kb() -> tuple[KBEntry, ...]:
    """Load every *.md file under apps/api/knowledge/drinkx/. Cached for the process."""
    if not _KB_PATH.exists():
        log.warning("kb.path_missing", path=str(_KB_PATH))
        return ()
    entries: list[KBEntry] = []
    for path in sorted(_KB_PATH.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        entry = _parse_one(path)
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def select_for_segment(segment: str | None) -> list[KBEntry]:
    """Pick the KB entries to inject for a given lead segment.

    Always-on entries (objections / competitors / ICP) are always included.
    For segment-specific playbooks: pick the highest-priority match.
    Returns at most 4 entries (3 always-on + 1 segment).
    """
    kb = load_kb()
    if not kb:
        return []

    always = [e for e in kb if e.always_on]
    selected: list[KBEntry] = list(always)

    if segment:
        seg = segment.strip().lower()
        matches = [
            e for e in kb
            if not e.always_on and any(s.lower() == seg for s in e.segments)
        ]
        matches.sort(key=lambda e: -e.priority)
        if matches:
            selected.append(matches[0])

    return selected


def render_kb_for_prompt(segment: str | None) -> str:
    """Format selected KB entries for inclusion in the synthesis system prompt."""
    entries = select_for_segment(segment)
    if not entries:
        return ""
    blocks: list[str] = []
    total = 0
    for e in entries:
        chunk = f"=== KB · {e.title} ===\n{e.body[:_PER_ENTRY_CHARS]}"
        if total + len(chunk) > _MAX_TOTAL_CHARS:
            break
        blocks.append(chunk)
        total += len(chunk)
    if not blocks:
        return ""
    return "\n\n".join(blocks)
