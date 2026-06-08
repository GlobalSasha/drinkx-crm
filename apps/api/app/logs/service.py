"""Read recent app logs back from the rotating JSON files.

api / worker / beat each write `app-<service>.log` into the shared LOG_DIR
(see `app.observability.configure_logging`). This module tails those files so
`GET /admin/logs` can return recent lines / errors without SSH — the same
source a future autonomous log-watcher (Celery beat) will read directly.
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_settings

_LEVEL_ORDER = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "warn": 30,
    "error": 40,
    "critical": 50,
    "exception": 40,
}


def _parse_since(since: str) -> timedelta | None:
    """'30m' / '2h' / '1d' / '90s' → timedelta. None if unparseable."""
    if not since:
        return None
    try:
        unit = since[-1].lower()
        value = int(since[:-1])
    except (ValueError, IndexError):
        return None
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit)
    return timedelta(seconds=value * mult) if mult else None


def _tail_lines(path: str, max_lines: int) -> list[str]:
    """Last `max_lines` lines. Files are size-capped (10MB) so reading the
    whole handle through a bounded deque is cheap and avoids seek math."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return list(deque(fh, maxlen=max_lines))
    except OSError:
        return []


def read_logs(
    *,
    level: str = "all",
    since: str = "1h",
    service: str | None = None,
    contains: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return recent log records (newest last), filtered by level / time /
    service / substring. `enabled=False` when LOG_DIR isn't configured."""
    settings = get_settings()
    log_dir = getattr(settings, "log_dir", "") or ""
    if not log_dir:
        return {"enabled": False, "lines": [], "summary": {},
                "note": "LOG_DIR not set — file logging disabled"}

    min_level = _LEVEL_ORDER.get(level.lower(), 0)
    delta = _parse_since(since)
    cutoff = datetime.now(timezone.utc) - delta if delta else None

    files = sorted(glob.glob(os.path.join(log_dir, "app-*.log*")))
    if service:
        files = [f for f in files if os.path.basename(f).startswith(f"app-{service}.")
                 or os.path.basename(f).startswith(f"app-{service}.log")]

    entries: list[dict[str, Any]] = []
    for path in files:
        svc = os.path.basename(path).split(".")[0].removeprefix("app-")
        for raw in _tail_lines(path, max_lines=5000):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                rec = {"event": raw, "level": "info"}
            rec.setdefault("service", svc)

            lvl = str(rec.get("level", "info")).lower()
            if _LEVEL_ORDER.get(lvl, 20) < min_level:
                continue
            if contains and contains.lower() not in raw.lower():
                continue
            if cutoff:
                ts = rec.get("timestamp")
                if ts:
                    try:
                        when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        if when.tzinfo is None:
                            when = when.replace(tzinfo=timezone.utc)
                        if when < cutoff:
                            continue
                    except ValueError:
                        pass
            entries.append(rec)

    entries.sort(key=lambda r: str(r.get("timestamp", "")))
    summary = Counter(str(e.get("level", "info")).lower() for e in entries)
    sliced = entries[-limit:]
    return {
        "enabled": True,
        "count": len(sliced),
        "total_matched": len(entries),
        "summary": dict(summary),
        "lines": sliced,
    }
