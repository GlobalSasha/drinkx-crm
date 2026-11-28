"""«Сводка за 5 дней»: the AI retells recent manager comments for the head.

Like the tags, the AI runs on the worker machine; the CRM checks what comes
back. A line is kept only if it is in a known section and names at least one
lead that really has comments in the period — so every line opens a lead the
reader can check. The list of new leads is not AI: it comes from the base.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.models import CommentDigest
from app.insights.schemas import DigestIn
from app.insights.services import _COMMENT_TEXT, _COMMENT_WHERE, scrub

DIGEST_DAYS = 5
DIGEST_STALE_HOURS = 36  # the worker runs nightly; more than a day and a half means it broke
MAX_LINE = 400
MAX_CLIENT = 80

# Fixed sections, in display order. The AI may use only these keys.
SECTIONS: dict[str, str] = {
    "progress": "Продвинулись",
    "objections": "Возражения и сомнения",
    "postponed": "Отложили или отказались",
    "attention": "Требует внимания",
}


async def _period_comments(
    db: AsyncSession, workspace_id: uuid.UUID, since: datetime, until: datetime
) -> list:
    return (await db.execute(text(f"""
        SELECT a.lead_id, a.created_at, {_COMMENT_TEXT} AS body, u.name AS author,
               l.company_name, l.city, s.name AS stage
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        LEFT JOIN users u ON u.id = a.user_id
        LEFT JOIN stages s ON s.id = l.stage_id
        WHERE {_COMMENT_WHERE} AND a.created_at >= :since AND a.created_at < :until
        ORDER BY l.company_name, a.created_at
    """), {"wid": workspace_id, "since": since, "until": until})).all()


async def digest_source(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    """Manager comments of the last DIGEST_DAYS, grouped by lead."""
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=DIGEST_DAYS)
    leads: dict[uuid.UUID, dict] = {}
    for r in await _period_comments(db, workspace_id, since, until):
        if not r.body.strip():
            continue
        lead = leads.setdefault(r.lead_id, {
            "lead_id": r.lead_id, "company_name": r.company_name,
            "stage": r.stage, "city": r.city, "comments": [],
        })
        lead["comments"].append({"at": r.created_at, "author": r.author, "text": scrub(r.body)})
    return {
        "period_from": since,
        "period_to": until,
        "sections": [{"key": k, "group": "digest", "label": v} for k, v in SECTIONS.items()],
        "leads": list(leads.values()),
    }


async def store_digest(db: AsyncSession, *, workspace_id: uuid.UUID, payload: DigestIn) -> dict:
    """Keep the lines that pass the checks; store them as the newest digest."""
    rows = await _period_comments(db, workspace_id, payload.period_from, payload.period_to)
    allowed = {r.lead_id for r in rows if r.body.strip()}
    accepted = dropped = 0
    sections: dict[str, list[dict]] = {}
    for section in payload.sections:
        for item in section.items:
            line = " ".join((item.text or "").split())
            client = " ".join((item.client or "").split())
            lead_ids = list(dict.fromkeys(i for i in item.lead_ids if i in allowed))
            if section.key not in SECTIONS or not line or len(line) > MAX_LINE or not lead_ids:
                dropped += 1
                continue
            sections.setdefault(section.key, []).append({
                "client": client if len(client) <= MAX_CLIENT else "",
                "text": line,
                "lead_ids": [str(i) for i in lead_ids],
            })
            accepted += 1
    db.add(CommentDigest(
        workspace_id=workspace_id,
        period_from=payload.period_from,
        period_to=payload.period_to,
        sections=[{"key": k, "items": sections[k]} for k in SECTIONS if k in sections],
    ))
    await db.flush()
    return {"accepted": accepted, "dropped": dropped}


async def company_digest(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    now = datetime.now(timezone.utc)
    latest = (await db.execute(
        select(CommentDigest)
        .where(CommentDigest.workspace_id == workspace_id)
        .order_by(CommentDigest.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    digest = None
    if latest is not None:
        rows = await _period_comments(db, workspace_id, latest.period_from, latest.period_to)
        rows = [r for r in rows if r.body.strip()]
        ids = {uuid.UUID(i) for s in latest.sections for it in s["items"] for i in it["lead_ids"]}
        names = {}
        if ids:
            names = dict((await db.execute(text("""
                SELECT id, company_name FROM leads
                WHERE workspace_id = :wid AND deleted_at IS NULL AND id = ANY(:ids)
            """), {"wid": workspace_id, "ids": list(ids)})).all())
        sections = []
        for s in latest.sections:
            items = []
            for it in s["items"]:
                leads = [{"id": uuid.UUID(i), "company_name": names[uuid.UUID(i)]}
                         for i in it["lead_ids"] if uuid.UUID(i) in names]
                if leads:  # a line about a lead deleted since is dropped
                    items.append({"client": it.get("client") or None, "text": it["text"],
                                  "leads": leads})
            if items and s["key"] in SECTIONS:
                sections.append({"key": s["key"], "title": SECTIONS[s["key"]], "items": items})
        digest = {
            "created_at": latest.created_at,
            "period_from": latest.period_from,
            "period_to": latest.period_to,
            "comments": len(rows),
            "leads": len({r.lead_id for r in rows}),
            "sections": sections,
        }

    new_from = now - timedelta(days=DIGEST_DAYS)
    new_leads = (await db.execute(text("""
        SELECT l.id, l.company_name, l.city, u.name AS manager, l.created_at,
               COALESCE(ls.name,
                        CASE WHEN l.source LIKE 'form:%' THEN 'Сайт' END,
                        NULLIF(l.source, '')) AS source
        FROM leads l
        LEFT JOIN users u ON u.id = l.assigned_to
        LEFT JOIN lead_sources ls ON ls.id = l.source_id
        WHERE l.workspace_id = :wid AND l.deleted_at IS NULL AND l.created_at >= :since
        ORDER BY l.created_at DESC
    """), {"wid": workspace_id, "since": new_from})).all()

    return {
        "digest": digest,
        "stale": latest is None or latest.created_at < now - timedelta(hours=DIGEST_STALE_HOURS),
        "new_leads_from": new_from,
        "new_leads": [
            {"id": r.id, "company_name": r.company_name, "city": r.city, "source": r.source,
             "manager": r.manager, "created_at": r.created_at}
            for r in new_leads
        ],
    }
