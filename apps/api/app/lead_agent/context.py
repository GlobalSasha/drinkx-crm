"""Lead AI Agent context builder — Sprint 3.1 Phase C.

Two responsibilities:
  1. Read the on-disk knowledge files once (lru_cache) and hand them
     back to the prompt builder. Files live at
     `apps/api/knowledge/agent/` — co-located with the API package so
     the existing `COPY knowledge ./knowledge` line in the Dockerfile
     ships them into the container at `/app/knowledge/agent/...`
     without a deploy-pipeline change.
  2. Render a compact, human-readable lead summary for the prompt
     `user` block. No DB lookups here — caller passes already-loaded
     `Lead` (and optionally a resolved `stage_name` since the model
     has only `stage_id`).

The knowledge root is found by walking up from `__file__` until we
hit a directory that contains `knowledge/agent/product-foundation.md`.
In dev that's `apps/api/`; in the production image it's `/app`.

Resolution is **lazy** and **soft-fail**: if the files aren't visible
to the running process, `load_product_foundation()` returns `""`
after a one-time warning. The runner falls back to a foundation-less
prompt rather than crashing module import — operations get a noisy
log, managers get a degraded but still functional agent.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

FOUNDATION_REL = Path("knowledge") / "agent" / "product-foundation.md"
SKILL_REL = Path("knowledge") / "agent" / "lead-ai-agent-skill.md"


@lru_cache(maxsize=1)
def _find_knowledge_root() -> Path | None:
    """Walk upwards until we find `knowledge/agent/product-foundation.md`.

    The agent knowledge files are co-located with the API package
    (`apps/api/knowledge/agent/`) so the existing `COPY knowledge ./knowledge`
    line in `apps/api/Dockerfile` ships them into the container at
    `/app/knowledge/agent/...`. In dev the walker finds them at
    `apps/api/`; in prod at `/app`. Returns `None` (not raises) if no
    parent contains the file — the runner is expected to handle that
    silently rather than crash the request.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / FOUNDATION_REL).is_file():
            return parent
    log.warning(
        "lead_agent.knowledge.root_missing",
        searched_from=str(here),
        looking_for=str(FOUNDATION_REL),
        message=(
            "Lead-agent knowledge files not found in any ancestor; the "
            "agent will run with an empty product-foundation block. "
            "Expected location: `apps/api/knowledge/agent/` (or "
            "`/app/knowledge/agent/` inside the API container)."
        ),
    )
    return None


def _read_relative(rel: Path) -> str:
    root = _find_knowledge_root()
    if root is None:
        return ""
    path = root / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning(
            "lead_agent.knowledge.read_failed",
            path=str(path),
            error=str(exc)[:200],
        )
        return ""


@lru_cache(maxsize=1)
def load_product_foundation() -> str:
    """Read `product-foundation.md` once per process. Returns the full
    file contents, or `""` if the file isn't reachable from this
    process. Caller may slice if it wants to bound prompt size."""
    return _read_relative(FOUNDATION_REL)


@lru_cache(maxsize=1)
def load_agent_skill() -> str:
    """Read `lead-ai-agent-skill.md` once per process. Currently only
    used by tests / ops debugging — the runtime prompts pull
    foundation only because the skill is the *behaviour* (encoded in
    `prompts.py`), not data the LLM should re-read every call.
    Returns `""` if the file isn't reachable."""
    return _read_relative(SKILL_REL)


def _truncate(value: Any, n: int) -> str:
    s = str(value or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def build_lead_context(lead: Any, *, stage_name: str | None = None) -> str:
    """Render the lead as a compact RU-language block for the prompt
    `user` slot.

    Caller responsibility:
      - `lead` is a loaded ORM `Lead` (or any object with the same
        attributes — duck-typed so tests can pass MagicMocks).
      - `stage_name` is optional. The model has only `stage_id`
        (UUID); rendering the human name is a separate JOIN we do
        upstream. When omitted the line is dropped entirely rather
        than printed as a UUID — UUIDs in a prompt are noise.
    """
    parts: list[str] = []
    company = getattr(lead, "company_name", None)
    parts.append(f"Компания: {_truncate(company, 200) or '(без названия)'}")

    segment = getattr(lead, "segment", None)
    if segment:
        parts.append(f"Сегмент: {_truncate(segment, 60)}")

    city = getattr(lead, "city", None)
    if city:
        parts.append(f"Город: {_truncate(city, 120)}")

    if stage_name:
        parts.append(f"Стадия: {_truncate(stage_name, 80)}")

    priority = getattr(lead, "priority", None)
    if priority:
        parts.append(f"Приоритет: {priority}")

    score = getattr(lead, "score", None)
    if score is not None:
        parts.append(f"Score: {score}/100")

    fit_score = getattr(lead, "fit_score", None)
    if fit_score is not None:
        parts.append(f"Fit: {fit_score}/10")

    deal_type = getattr(lead, "deal_type", None)
    if deal_type:
        parts.append(f"Тип сделки: {deal_type}")

    next_step = getattr(lead, "next_step", None)
    if next_step:
        parts.append(f"Следующий шаг: {_truncate(next_step, 300)}")

    blocker = getattr(lead, "blocker", None)
    if blocker:
        parts.append(f"Блокер: {_truncate(blocker, 300)}")

    # AI Brief — the synthesis output stored in `lead.ai_data` carries
    # `company_profile` (per ResearchOutput schema), NOT `summary`.
    ai_data = getattr(lead, "ai_data", None) or {}
    if isinstance(ai_data, dict):
        profile = ai_data.get("company_profile") or ""
        if profile:
            parts.append(f"AI-бриф: {_truncate(profile, 500)}")

    return "\n".join(parts)
