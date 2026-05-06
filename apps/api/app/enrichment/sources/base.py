"""Source contract — every source returns a uniform shape."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceResult:
    """Common return type from every source.fetch() call."""
    source: str                       # "brave" | "hh" | "web_fetch"
    query: str                        # what was queried (URL or term)
    items: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None                   # raw payload for debugging
    cached: bool = False              # True if served from Redis
    elapsed_ms: int = 0
    error: str = ""                   # populated on fail-soft (items will be empty)


class SourceError(Exception):
    """Catastrophic source failure (timeout, 5xx) — caller decides whether to abort."""
    def __init__(self, message: str, *, source: str, status: int | None = None):
        super().__init__(message)
        self.source = source
        self.status = status
