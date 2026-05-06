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

from app.enrichment.models import EnrichmentRun
from app.enrichment.providers.base import LLMError, TaskType
from app.enrichment.providers.factory import complete_with_fallback
from app.enrichment.schemas import ResearchOutput
from app.enrichment.sources.base import SourceResult
from app.enrichment.sources.brave import BraveSearch
from app.enrichment.sources.hh import HHRu
from app.enrichment.sources.web_fetch import WebFetch
from app.leads.models import Lead

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYNTHESIS_SYSTEM = """Ты — research-аналитик DrinkX, B2B бренда умных кофе-станций.
Получаешь лид и снэпшоты из Brave / HH.ru / сайта компании.

ПРАВИЛА ВЫВОДА (нарушение = сломанный pipeline):
1. Возвращай РОВНО ОДИН JSON-объект. Без markdown, без ```code fences```,
   без преамбулы, без комментариев. Первый символ — `{`, последний — `}`.
2. Не размышляй вслух — никакого reasoning перед JSON.
3. Все поля схемы обязательны. Если данных нет — пустая строка "" или [].
4. company_profile — РОВНО 2-3 предложения, не больше.
5. fit_score — число 0..10, без кавычек.
6. Не выдумывай decision_maker_hints, если их нет в источниках. Лучше [].

СХЕМА:
{
  "company_profile": str,
  "network_scale": str,
  "geography": str,
  "formats": str,
  "coffee_signals": str,
  "growth_signals": [str, ...],
  "risk_signals": [str, ...],
  "decision_maker_hints": [{"name": str, "title": str, "role": "economic_buyer|champion|technical_buyer|operational_buyer|", "confidence": "high|medium|low", "source": str}, ...],
  "fit_score": number,
  "next_steps": [str, ...],
  "urgency": "high|medium|low|",
  "sources_used": [str, ...],
  "notes": str
}"""

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


def _format_brave_block(results: list[SourceResult]) -> str:
    lines: list[str] = []
    for sr in results:
        for item in sr.items[:5]:
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            lines.append(f"- {title}\n  URL: {url}\n  {desc}")
    return "\n".join(lines) if lines else "(нет результатов)"


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

async def run_enrichment(*, db: AsyncSession, run_id: UUID) -> None:
    """Execute Research Agent pipeline for the EnrichmentRun row identified by run_id.

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

    try:
        # Load lead
        lead_result = await db.execute(select(Lead).where(Lead.id == run.lead_id))
        lead: Lead | None = lead_result.scalar_one_or_none()
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
        brave_block = _format_brave_block(brave_results)
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
        completion = await complete_with_fallback(
            system=SYNTHESIS_SYSTEM,
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

        lead.ai_data = research_output.model_dump()
        if research_output.fit_score and research_output.fit_score > 0:
            lead.fit_score = research_output.fit_score

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

        await db.commit()

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
            run.status = "failed"
            run.error = f"{error_type}: {exc}"[:1000]
            run.duration_ms = duration_ms
            run.finished_at = datetime.now(tz=timezone.utc)
            await db.commit()
        except Exception as commit_exc:
            bound_log.error("enrichment.commit_failed", error=str(commit_exc)[:200])
