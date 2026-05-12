"""Research Agent orchestrator — ties providers + sources into a pipeline.

Pipeline per ADR (01_ARCHITECTURE.md):
  1. Build queries from lead data
  2. Parallel fetch: Brave (N queries) + HH.ru + optional WebFetch
  3. Compose synthesis prompt
  4. Call LLM via complete_with_fallback(research_synthesis)
  5. Parse ResearchOutput; fallback to defaults on parse failure
  6. Persist result to lead.ai_data + update EnrichmentRun row

The function never raises — all failures are caught and written to the run row.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enrichment.budget import add_to_daily_spend
from app.enrichment.kb import render_kb_for_prompt
from app.enrichment.models import EnrichmentRun
from app.enrichment.profile import render_profile_for_prompt
from app.enrichment.providers.base import LLMError, TaskType
from app.enrichment.providers.factory import complete_with_fallback
from app.enrichment.schemas import FoundContact, ResearchOutput
from app.contacts.models import Contact
from app.enrichment.sources.base import SourceResult
from app.enrichment.sources.brave import BraveSearch
from app.enrichment.sources.hh import HHRu
from app.enrichment.sources.web_fetch import WebFetch
from app.leads.models import Lead
from app.activity.models import Activity

log = structlog.get_logger()

# Cap on the email-context block injected into the synthesis prompt.
# Single source of truth for both the helper and the test suite.
EMAIL_CONTEXT_MAX_CHARS = 2000
EMAIL_BODY_PREVIEW_CHARS = 200

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYNTHESIS_SYSTEM = """Ты — sales-аналитик DrinkX (умные кофе-станции для розницы и HoReCa).
Получаешь лид и снэпшоты из Brave / HH.ru / сайта компании. Готовишь brief
для менеджера продаж — кратко, по-человечески, без технического жаргона.

СТИЛЬ:
- Простой деловой русский, как пишут аккаунт-менеджеры. Уместно: "сеть",
  "магазины", "филиалы", "оборот", "закупки", "решения по закупкам",
  "офис компании".
- НЕ употребляй: "ритейлер", "email-рассылки", "B2B", "ROI",
  "кофейные технологии", "кофепойнты", "стейкхолдеры", "ICP",
  "закупочная команда", "operational excellence".
- Конкретика без воды. Если не уверен — пустое поле, не выдумывай.
- Не выдумывай decision_maker_hints. Если в источниках нет имени и
  должности — оставляй [].

ПРАВИЛА ВЫВОДА:
1. Возвращай РОВНО ОДИН JSON-объект. Без markdown, без ```code fences```,
   без преамбулы. Первый символ — `{`, последний — `}`.
2. Никакого reasoning перед JSON.
3. company_profile — 2 предложения максимум, по-делу.
4. fit_score — число 0..10, без кавычек.
5. role в decision_maker_hints — только одно из:
   "economic_buyer" | "champion" | "technical_buyer" | "operational_buyer" | ""
   (английские технические значения; в UI они переводятся на русский).
6. confidence — "high" | "medium" | "low".
7. urgency — "high" | "medium" | "low" | "".
8. score_rationale — 2–3 предложения, почему такой fit_score. Опирайся на конкретные
   сигналы из Brave / HH.ru / сайта. Используй шкалу из KB · icp_definition.

СХЕМА:
{
  "company_profile": str,
  "network_scale": str,
  "geography": str,
  "formats": [str, ...],
  "coffee_signals": [str, ...],
  "growth_signals": [str, ...],
  "risk_signals": [str, ...],
  "decision_maker_hints": [
    {"name": str, "title": str, "role": str, "confidence": str, "source": str}
  ],
  "fit_score": number,
  "score_rationale": str,
  "next_steps": [str, ...],
  "urgency": str,
  "sources_used": [str, ...],
  "notes": str
}"""

# Segment-specific role lists for contact extraction. Lead.segment is a
# free-form string, so we normalise (lowercase + strip + replace common
# separators) before lookup. Falls back to GENERIC_CONTACT_ROLES when the
# segment is missing or doesn't match a known bucket.
SEGMENT_CONTACT_ROLES: dict[str, list[str]] = {
    "horeca": [
        "шеф-бариста", "бар-менеджер", "F&B менеджер",
        "food & beverage director", "операционный директор",
        "управляющий", "закупки напитки",
    ],
    "retail_grocery": [
        "категорийный менеджер кофе",
        "категорийный менеджер готовая еда",
        "коммерческий директор", "директор по закупкам",
        "менеджер по категории non-food",
    ],
    "qsr": [
        "операционный директор", "директор по франчайзингу",
        "менеджер по оборудованию", "технический директор",
    ],
    "gas_stations": [
        "директор по развитию", "менеджер по кофе-программе",
        "коммерческий директор", "менеджер по немоторному бизнесу",
    ],
    "office": [
        "офис-менеджер", "административный директор",
        "HR директор", "менеджер по АХО",
    ],
}

GENERIC_CONTACT_ROLES = [
    "категорийный менеджер", "директор по закупкам",
    "операционный директор", "коммерческий директор",
    "руководитель направления",
]


def _roles_for_segment(segment: str | None) -> list[str]:
    """Map free-form Lead.segment to a curated role list. Permissive — if
    nothing matches, returns the generic set (the prompt still works, just
    less targeted)."""
    if not segment:
        return GENERIC_CONTACT_ROLES
    key = segment.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
    # Aliases for common Russian-language values seen in production data.
    aliases = {
        "horeca": "horeca",
        "хорека": "horeca",
        "horeka": "horeca",
        "retail": "retail_grocery",
        "retail_grocery": "retail_grocery",
        "ритейл": "retail_grocery",
        "ритейл_grocery": "retail_grocery",
        "продуктовый_ритейл": "retail_grocery",
        "qsr": "qsr",
        "fast_food": "qsr",
        "qsr_fast_food": "qsr",
        "azs": "gas_stations",
        "азс": "gas_stations",
        "gas_stations": "gas_stations",
        "office": "office",
        "офис": "office",
        "b2b": "office",
        "офис_b2b": "office",
    }
    canonical = aliases.get(key, key)
    return SEGMENT_CONTACT_ROLES.get(canonical, GENERIC_CONTACT_ROLES)


# Focused contact-extraction prompt — runs as a separate LLM call after main
# synthesis. Keeps the response budget small so it doesn't share a context
# window with the long Brief output (where trailing fields like contacts_found
# were getting truncated by MiMo).
CONTACT_EXTRACTION_SYSTEM_TMPL = """Ты извлекаешь имена людей из текста.
Верни ТОЛЬКО JSON-массив, без markdown, без ```code fences``` и преамбулы.
Первый символ — `[`, последний — `]`.

Формат каждого элемента:
{{"name": "Имя Фамилия", "title": "Должность",
 "source": "откуда (HH.ru / сайт / статья / LinkedIn)",
 "confidence": число 0.0–1.0}}

Правила:
- Только реальные люди, упомянутые в тексте по имени.
- Не выдумывай. Если имён в тексте нет — верни [].
- confidence: 0.8+ если имя+должность напрямую упомянуты,
  0.5–0.7 если выводится по контексту. Меньше 0.5 — не добавляй.
- Целевые должности для этого сегмента (приоритет таким):
{target_roles_block}"""

CONTACT_EXTRACTION_USER_TMPL = """Текст:
{sources_text}

Верни JSON-массив. Только массив, без объяснений."""

# Hard cap on the source text fed into the contact-extraction call.
CONTACT_EXTRACTION_SOURCE_CHARS = 3000


USER_TMPL = """Компания: {company_name}
Сегмент: {segment}
Город: {city}
Сайт: {website}

Brave (топ результатов):
{brave_block}

HH.ru вакансии:
{hh_block}

Сайт компании (фрагмент):
{web_block}

Верни JSON по схеме. Только JSON, без объяснений."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_queries(lead: Lead) -> list[str]:
    """Derive Brave search queries from lead fields. No LLM in Phase C."""
    company = lead.company_name or ""
    city = lead.city or ""
    queries = [
        f"{company} официальный сайт",
        f"{company} {city}".strip(),
        f"{company} закупки руководитель",
    ]
    return [q for q in queries if q.strip()]


def _format_brave_block(results: list[SourceResult], max_chars: int | None = None) -> str:
    """Format Brave results for the synthesis prompt.

    `max_chars` truncates the joined block — used on re-enrichment of large
    leads (e.g. Пятёрочка) where the full Brave dump balloons the prompt
    and pushes the LLM into timeouts. Truncation is char-based with an
    explicit suffix so the LLM doesn't try to interpret a half-cut line.
    """
    lines: list[str] = []
    for sr in results:
        for item in sr.items[:5]:
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            lines.append(f"- {title}\n  URL: {url}\n  {desc}")
    block = "\n".join(lines) if lines else "(нет результатов)"
    if max_chars is not None and len(block) > max_chars:
        block = block[:max_chars].rstrip() + "\n…(обрезано)"
    return block


def _format_hh_block(result: SourceResult) -> str:
    if not result.items:
        return "(нет вакансий)"
    lines: list[str] = []
    for item in result.items[:10]:
        title = item.get("title", "")
        company = item.get("company", "")
        city = item.get("city", "")
        url = item.get("url", "")
        lines.append(f"- {title} | {company} | {city}\n  {url}")
    return "\n".join(lines)


def _format_web_block(result: SourceResult | None) -> str:
    if result is None or not result.items:
        return "(сайт не загружен)"
    item = result.items[0]
    text = item.get("text", "")
    return text[:3000] if text else "(пустой сайт)"


# Float confidence threshold for auto-creating a Contact from FoundContact.
# Below this we trust the LLM's hint but won't pollute the contacts list.
# Lowered from 0.5 → 0.3 because LLMs were too conservative; contacts are
# always created as verified_status='to_verify' so the manager confirms.
CONTACT_AUTOCREATE_MIN_CONFIDENCE = 0.3


def _confidence_float_to_bucket(value: float) -> str:
    """Map FoundContact.confidence (0..1) to Contact.confidence string bucket.
    Contact.confidence is String(20) with values high/medium/low (no migration)."""
    if value >= 0.8:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _build_extraction_source_text(
    brave_results: list[SourceResult],
    hh_result: SourceResult,
    web_result: SourceResult | None,
) -> str:
    """Concatenate raw source snippets for the contact-extraction call.
    Capped at CONTACT_EXTRACTION_SOURCE_CHARS so a long Brave dump or web
    fetch can't blow up the prompt — that's exactly what was causing
    trailing-field truncation in the bundled synthesis."""
    parts: list[str] = []

    # HH first — vacancies often name a hiring manager
    if hh_result.items:
        for item in hh_result.items[:10]:
            title = item.get("title", "")
            company = item.get("company", "")
            city = item.get("city", "")
            parts.append(f"HH: {title} | {company} | {city}")

    # Brave titles + descriptions
    for sr in brave_results:
        for item in sr.items[:5]:
            title = item.get("title", "")
            desc = item.get("description", "")
            parts.append(f"Brave: {title} — {desc}")

    # Website excerpt last — long but useful
    if web_result and web_result.items:
        text = web_result.items[0].get("text", "")
        if text:
            parts.append(f"Сайт: {text}")

    joined = "\n".join(parts)
    if len(joined) > CONTACT_EXTRACTION_SOURCE_CHARS:
        joined = joined[:CONTACT_EXTRACTION_SOURCE_CHARS].rstrip() + "\n…(обрезано)"
    return joined


async def _extract_contacts_from_sources(
    *,
    brave_results: list[SourceResult],
    hh_result: SourceResult,
    web_result: SourceResult | None,
    segment: str | None = None,
) -> list[FoundContact]:
    """Focused second LLM call to pull named people out of the raw sources.

    `segment` selects a curated role list (SEGMENT_CONTACT_ROLES) injected
    into the prompt — keeps the model focused on roles that actually buy
    coffee equipment in that vertical. Falls back to GENERIC_CONTACT_ROLES.

    Returns [] on any failure (parse error, LLM timeout, etc.) so the rest
    of the enrichment pipeline never depends on this call succeeding.
    """
    sources_text = _build_extraction_source_text(brave_results, hh_result, web_result)
    if not sources_text.strip():
        return []

    target_roles = _roles_for_segment(segment)
    target_roles_block = "\n".join(f"  - {r}" for r in target_roles)
    system_prompt = CONTACT_EXTRACTION_SYSTEM_TMPL.format(
        target_roles_block=target_roles_block,
    )
    user_prompt = CONTACT_EXTRACTION_USER_TMPL.format(sources_text=sources_text)

    try:
        completion = await complete_with_fallback(
            system=system_prompt,
            user=user_prompt,
            task_type=TaskType.research_synthesis,
            max_tokens=1000,
            temperature=0.2,
        )
    except LLMError as e:
        log.warning("enrichment.contact_extraction_failed", reason=str(e)[:200])
        return []

    raw = completion.text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]).strip() if len(lines) > 2 else raw

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("enrichment.contact_extraction_parse_failed", raw_preview=raw[:200])
        return []

    if not isinstance(data, list):
        log.warning("enrichment.contact_extraction_wrong_shape", got=type(data).__name__)
        return []

    contacts: list[FoundContact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            contacts.append(FoundContact(**item))
        except (ValidationError, TypeError):
            continue
    return contacts


async def _materialise_found_contacts(
    db: AsyncSession,
    lead: Lead,
    found: list[FoundContact],
) -> int:
    """Create Contact rows for FoundContacts above the confidence threshold.

    Skip rules (per FEATURE spec):
      - confidence < CONTACT_AUTOCREATE_MIN_CONFIDENCE
      - email matches an existing Contact on this lead (case-insensitive)
      - name matches an existing Contact on this lead (case-insensitive)

    Caller commits — we only stage rows on the session. Always emits a
    structlog summary (even when 0 created) so we can distinguish "LLM
    returned nothing" from "all entries filtered" in production.
    """
    skipped_low_confidence = 0
    skipped_no_name = 0
    skipped_dup_email = 0
    skipped_dup_name = 0

    if not found:
        log.info(
            "enrichment.contacts_summary",
            lead_id=str(lead.id),
            input_count=0,
            created=0,
        )
        return 0

    existing = await db.execute(select(Contact).where(Contact.lead_id == lead.id))
    existing_contacts = existing.scalars().all()
    existing_emails = {_norm(c.email) for c in existing_contacts if c.email}
    existing_names = {_norm(c.name) for c in existing_contacts if c.name}

    created = 0
    for fc in found:
        if fc.confidence < CONTACT_AUTOCREATE_MIN_CONFIDENCE:
            skipped_low_confidence += 1
            continue
        name_key = _norm(fc.name)
        email_key = _norm(fc.email)
        if not name_key:
            skipped_no_name += 1
            continue
        if email_key and email_key in existing_emails:
            skipped_dup_email += 1
            continue
        if name_key in existing_names:
            skipped_dup_name += 1
            continue

        contact = Contact(
            lead_id=lead.id,
            workspace_id=lead.workspace_id,
            name=fc.name.strip(),
            title=fc.title,
            email=fc.email,
            phone=fc.phone,
            linkedin_url=fc.linkedin_url,
            source=(fc.source or "AI")[:40],
            verified_status="to_verify",
            confidence=_confidence_float_to_bucket(fc.confidence),
        )
        db.add(contact)
        existing_names.add(name_key)
        if email_key:
            existing_emails.add(email_key)
        created += 1

    # Flush staged contacts now so any INSERT error surfaces here (caught by
    # the orchestrator's outer except) instead of being deferred to commit
    # time, where a later session-poisoning bug could mask it. The caller
    # still owns the final commit — flush only sends the rows to the DB
    # within the open transaction.
    if created:
        await db.flush()

    log.info(
        "enrichment.contacts_summary",
        lead_id=str(lead.id),
        input_count=len(found),
        created=created,
        skipped_low_confidence=skipped_low_confidence,
        skipped_no_name=skipped_no_name,
        skipped_dup_email=skipped_dup_email,
        skipped_dup_name=skipped_dup_name,
    )
    return created


def _collect_sources_used(
    brave_results: list[SourceResult],
    hh_result: SourceResult,
    web_result: SourceResult | None,
) -> list[str]:
    used: list[str] = []
    for sr in brave_results:
        if sr.items and "brave" not in used:
            used.append("brave")
    if hh_result.items and "hh" not in used:
        used.append("hh")
    if web_result and web_result.items and "web_fetch" not in used:
        used.append("web_fetch")
    return used


async def _load_email_context(
    session: AsyncSession, lead_id: Any, *, limit: int = 10
) -> str:
    """Format the last `limit` email Activities for synthesis-prompt injection.

    Returns a formatted block prefixed with the section preamble, or "" when
    no emails exist (caller skips injection). Each line marks direction with
    ← / → and shows subject + first ~200 chars of body. Per ADR-019 the feed
    is lead-scoped — `Activity.user_id` is NOT a filter here; every email
    that touched this lead surfaces in the AI Brief regardless of which
    manager's mailbox sourced it.
    """
    res = await session.execute(
        select(Activity)
        .where(Activity.lead_id == lead_id)
        .where(Activity.type == "email")
        .order_by(Activity.created_at.desc())
        .limit(limit)
    )
    rows = list(res.scalars())
    if not rows:
        return ""

    lines: list[str] = ["Переписка с клиентом (последние письма):"]
    for a in rows:
        marker = "← Входящее" if (a.direction or "") != "outbound" else "→ Исходящее"
        subject = (a.subject or "(без темы)").strip()
        body_preview = ((a.body or "").strip())[:EMAIL_BODY_PREVIEW_CHARS]
        # Replace newlines so each email stays a single prompt line —
        # multi-line bodies otherwise break the LLM's section parsing.
        body_preview = body_preview.replace("\n", " ").replace("\r", " ")
        lines.append(f"[{marker}] Тема: {subject} | {body_preview}")
    return "\n".join(lines)


def _format_email_section(email_ctx: str) -> str:
    """Wrap the (already-truncated) email context in a synthesis-prompt section."""
    return (
        "### Переписка с клиентом\n"
        f"{email_ctx}\n\n"
        "Используй переписку как сигнал реального интереса или возражений. "
        "Не пересказывай письма — только учитывай как контекст для оценки."
    )


def _parse_research_output(text: str) -> tuple[ResearchOutput, bool]:
    """Return (ResearchOutput, parse_ok). On failure returns defaults with raw in notes."""
    # Strip possible markdown code fence
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop first and last fence lines
        inner = "\n".join(lines[1:-1]) if len(lines) > 2 else stripped
        stripped = inner.strip()

    try:
        data = json.loads(stripped)
        output = ResearchOutput(**data)
        return output, True
    except (json.JSONDecodeError, ValidationError, TypeError):
        log.warning("enrichment.parse_failed", raw_preview=stripped[:200])
        return ResearchOutput(notes=text[:2000]), False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _merge_append_only(existing: dict, incoming: dict) -> dict:
    """Append-only merge: keep every key from `existing` that has a truthy
    value; fill missing/empty keys from `incoming`.

    Used by enrichment `mode='append'` — manager presses «Дополнить» and
    expects the existing brief to stay intact, with AI filling holes only.

    Truthy = non-empty string, non-empty list, non-zero number, etc.
    Falsy = `""`, `[]`, `{}`, `0`, `0.0`, `None`. Note: `0` is treated as
    empty so `fit_score=0.0` defaults can be overwritten by real values.
    """
    merged = dict(existing)
    for key, new_val in incoming.items():
        cur = merged.get(key)
        if not cur:
            merged[key] = new_val
    return merged


async def run_enrichment(
    *,
    db: AsyncSession,
    run_id: UUID,
    mode: str = "full",
) -> None:
    """Execute Research Agent pipeline for the EnrichmentRun row identified by run_id.

    `mode`:
      - "full" (default): overwrite `lead.ai_data` with the new ResearchOutput dump.
      - "append": merge into existing `lead.ai_data` — fill only empty keys,
        keep populated ones intact.

    Idempotent: callers can re-run; this updates the same row.
    Never raises — all failures are written to the run row as status=failed.
    """
    # Load the run row
    run_result = await db.execute(select(EnrichmentRun).where(EnrichmentRun.id == run_id))
    run: EnrichmentRun | None = run_result.scalar_one_or_none()
    if run is None:
        log.error("enrichment.run_not_found", run_id=str(run_id))
        return

    bound_log = log.bind(run_id=str(run_id), lead_id=str(run.lead_id))
    bound_log.info("enrichment.started")

    wall_start = time.perf_counter()
    lead: Lead | None = None  # bound here so the failure path can read it

    try:
        # Load lead
        lead_result = await db.execute(select(Lead).where(Lead.id == run.lead_id))
        lead = lead_result.scalar_one_or_none()
        if lead is None:
            raise ValueError(f"Lead {run.lead_id} not found")

        # --- Step 1: Build queries ---
        brave_queries = _build_queries(lead)
        hh_query = lead.company_name or ""

        # --- Step 2: Parallel fetch ---
        brave_source = BraveSearch()
        hh_source = HHRu()
        web_source = WebFetch()

        fetch_tasks: list[Any] = [
            brave_source.fetch(q, use_cache=True) for q in brave_queries
        ]
        fetch_tasks.append(hh_source.fetch(hh_query, use_cache=True))

        has_website = bool(lead.website and lead.website.strip())
        if has_website:
            fetch_tasks.append(web_source.fetch(lead.website, use_cache=True))  # type: ignore[arg-type]

        raw_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # Separate results
        brave_results: list[SourceResult] = []
        hh_result: SourceResult = SourceResult(source="hh", query=hh_query)
        web_result: SourceResult | None = None

        n_brave = len(brave_queries)
        for i, r in enumerate(raw_results):
            if isinstance(r, Exception):
                bound_log.warning("enrichment.source_error", index=i, error=str(r))
                continue
            if i < n_brave:
                brave_results.append(r)
            elif i == n_brave:
                hh_result = r
            else:
                web_result = r

        sources_used = _collect_sources_used(brave_results, hh_result, web_result)

        # --- Step 3: Compose synthesis prompt ---
        # Re-enrichment of large retailers can blow past the model's context
        # budget; cap Brave at 2000 chars when ai_data is already populated.
        is_reenrichment = lead.ai_data is not None
        brave_block = _format_brave_block(
            brave_results,
            max_chars=2000 if is_reenrichment else None,
        )
        hh_block = _format_hh_block(hh_result)
        web_block = _format_web_block(web_result)

        user_prompt = USER_TMPL.format(
            company_name=lead.company_name or "",
            segment=lead.segment or "",
            city=lead.city or "",
            website=lead.website or "",
            brave_block=brave_block,
            hh_block=hh_block,
            web_block=web_block,
        )

        # --- Step 4: LLM synthesis ---
        profile_block = render_profile_for_prompt()
        kb_block = render_kb_for_prompt(lead.segment)
        email_ctx = await _load_email_context(db, lead.id)
        if email_ctx and len(email_ctx) > EMAIL_CONTEXT_MAX_CHARS:
            email_ctx = email_ctx[:EMAIL_CONTEXT_MAX_CHARS]

        system_parts = []
        if profile_block:
            system_parts.append(profile_block)
        if kb_block:
            system_parts.append(kb_block)
        if email_ctx:
            system_parts.append(_format_email_section(email_ctx))
        system_parts.append(SYNTHESIS_SYSTEM)
        system_prompt = "\n\n".join(system_parts)
        completion = await complete_with_fallback(
            system=system_prompt,
            user=user_prompt,
            task_type=TaskType.research_synthesis,
            max_tokens=2048,
            temperature=0.3,
        )

        # --- Step 5: Parse output ---
        research_output, parse_ok = _parse_research_output(completion.text)
        if not parse_ok:
            bound_log.warning("enrichment.output_parse_failed")

        # Merge sources_used from LLM output with our observed list
        if research_output.sources_used:
            for s in research_output.sources_used:
                if s not in sources_used:
                    sources_used.append(s)
        else:
            research_output = research_output.model_copy(update={"sources_used": sources_used})

        # --- Step 6: Persist ---
        duration_ms = int((time.perf_counter() - wall_start) * 1000)

        new_dump = research_output.model_dump()
        if mode == "append" and lead.ai_data:
            lead.ai_data = _merge_append_only(lead.ai_data, new_dump)
            bound_log.info(
                "enrichment.merged_append",
                filled=[k for k in new_dump if not (lead.ai_data.get(k) is new_dump.get(k))],
            )
        else:
            lead.ai_data = new_dump
        if research_output.fit_score and research_output.fit_score > 0:
            # Append mode: only fill if column is null/zero — matches semantics.
            if mode != "append" or not lead.fit_score:
                lead.fit_score = research_output.fit_score

        # Focused second LLM call — extract named people from the raw sources.
        # Separate from the main synthesis because MiMo was truncating
        # trailing fields when contacts_found was bundled into the long Brief
        # response. Failure-tolerant — empty list on any error.
        extracted_contacts = await _extract_contacts_from_sources(
            brave_results=brave_results,
            hh_result=hh_result,
            web_result=web_result,
            segment=lead.segment,
        )
        bound_log.info(
            "enrichment.contacts_extracted",
            count=len(extracted_contacts),
        )

        # Auto-materialise high-confidence FoundContacts as Contact rows
        # (verified_status='to_verify' — manager confirms or deletes in UI).
        # The helper emits its own structlog summary.
        await _materialise_found_contacts(db, lead, extracted_contacts)

        run.status = "succeeded"
        run.provider = completion.provider
        run.model = completion.model
        run.prompt_tokens = completion.prompt_tokens
        run.completion_tokens = completion.completion_tokens
        run.cost_usd = Decimal(str(round(completion.cost_usd, 4)))
        run.duration_ms = duration_ms
        run.sources_used = sources_used
        run.result_json = research_output.model_dump()
        run.finished_at = datetime.now(tz=timezone.utc)

        # Notify the lead's current owner (unassigned leads have assigned_to=NULL — skip).
        # Run inside a SAVEPOINT so a notification flush failure (e.g. FK
        # violation if the assignee was deleted) rolls back only the
        # notification — contacts and ai_data must survive.
        if lead.assigned_to is not None:
            from app.notifications.services import notify

            company = lead.company_name or "—"
            try:
                async with db.begin_nested():
                    await notify(
                        db,
                        workspace_id=lead.workspace_id,
                        user_id=lead.assigned_to,
                        kind="enrichment_done",
                        title=f"AI Brief готов: {company}",
                        body=research_output.company_profile[:300] if research_output.company_profile else "",
                        lead_id=lead.id,
                    )
            except Exception as notify_exc:
                bound_log.warning(
                    "enrichment.notify_failed",
                    error=str(notify_exc)[:200],
                )

        await db.commit()
        bound_log.info("enrichment.commit_done")

        # Track daily spend in Redis (best-effort, never fail the run)
        await add_to_daily_spend(lead.workspace_id, completion.cost_usd)

        bound_log.info(
            "enrichment.succeeded",
            provider=run.provider,
            cost_usd=float(run.cost_usd),
            duration_ms=run.duration_ms,
            sources=sources_used,
        )

    except Exception as exc:
        duration_ms = int((time.perf_counter() - wall_start) * 1000)
        error_type = type(exc).__name__
        bound_log.error(
            "enrichment.failed",
            error_type=error_type,
            error=str(exc)[:500],
            duration_ms=duration_ms,
        )
        try:
            # If `exc` came from a flush, the session's transaction is
            # already rolled back and any subsequent write raises
            # InvalidRequestError. Rolling back explicitly resets the
            # session to a usable state so the run.status='failed' write
            # below can commit — otherwise the row strands at 'running'
            # and the lead's AI Brief button stays disabled forever.
            try:
                await db.rollback()
            except Exception:
                pass

            run.status = "failed"
            run.error = f"{error_type}: {exc}"[:1000]
            run.duration_ms = duration_ms
            run.finished_at = datetime.now(tz=timezone.utc)

            # `lead` may be None if the failure happened during lookup —
            # in that case we have no workspace_id to attribute, so skip.
            # Notify the lead's owner; unassigned leads have no recipient.
            # Wrapped in begin_nested so a notify error doesn't prevent the
            # run.status='failed' commit from going through.
            if lead is not None and lead.assigned_to is not None:
                from app.notifications.services import notify

                company = lead.company_name or "—"
                try:
                    async with db.begin_nested():
                        await notify(
                            db,
                            workspace_id=lead.workspace_id,
                            user_id=lead.assigned_to,
                            kind="enrichment_failed",
                            title=f"AI Brief не собрался: {company}",
                            body=f"{error_type}: {str(exc)[:200]}",
                            lead_id=lead.id,
                        )
                except Exception as notify_exc:
                    bound_log.warning(
                        "enrichment.notify_failed",
                        error=str(notify_exc)[:200],
                    )

            await db.commit()
        except Exception as commit_exc:
            bound_log.error("enrichment.commit_failed", error=str(commit_exc)[:200])
