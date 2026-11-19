"""«Голос клиентов»: hand comments to the AI worker, take its tags back, and
sum them up for the head's /today.

The AI runs outside the CRM (a worker on a machine with a Claude
subscription). Everything it sends is checked here: the category must be one
of CATEGORIES and the quote must really be in the comment — otherwise the tag
is dropped. So the card never shows a reason nobody wrote.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.categories import CATEGORIES, GROUP_LABELS, normalize_competitor
from app.insights.models import CommentInsight, CommentInsightScan
from app.insights.schemas import IngestIn

BACKFILL_DAYS = 30
MAX_ATTEMPTS = 3
QUOTES_PER_ITEM = 5
GROUP_ORDER = ["objection", "question", "interest", "competitor", "contact"]

# A manager comment: typed by a person, not archived, on a live lead.
_COMMENT_TEXT = "COALESCE(NULLIF(a.body, ''), a.payload_json->>'text', '')"
_COMMENT_WHERE = """
    a.type = 'comment' AND a.user_id IS NOT NULL AND a.archived_at IS NULL
    AND l.workspace_id = :wid AND l.deleted_at IS NULL
"""

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Phone-like runs: 10+ digits with spaces, dashes, brackets or a leading +.
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")


def scrub(text_: str) -> str:
    """Cut out e-mails and phone numbers before the text leaves the CRM."""
    return _PHONE_RE.sub("[телефон]", _EMAIL_RE.sub("[почта]", text_))


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[«»\"'“”„]", "", s)
    return " ".join(s.split())


def quote_in_comment(quote: str, comment: str) -> bool:
    q = _norm(quote)
    return len(q) >= 3 and q in _norm(comment)


async def pending_comments(
    db: AsyncSession, *, workspace_id: uuid.UUID, limit: int = 60
) -> list[dict]:
    """Comments the AI has not tagged yet, oldest first, from the last
    BACKFILL_DAYS. A comment that failed MAX_ATTEMPTS times is left alone."""
    since = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)
    rows = (await db.execute(text(f"""
        SELECT a.id, {_COMMENT_TEXT} AS body
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        LEFT JOIN comment_insight_scans s ON s.activity_id = a.id
        WHERE {_COMMENT_WHERE} AND a.created_at >= :since
          AND (s.activity_id IS NULL OR (s.status = 'failed' AND s.attempts < :max_attempts))
        ORDER BY a.created_at
        LIMIT :limit
    """), {"wid": workspace_id, "since": since, "max_attempts": MAX_ATTEMPTS, "limit": limit})).all()
    return [{"activity_id": r.id, "text": scrub(r.body)} for r in rows if r.body.strip()]


async def ingest(db: AsyncSession, *, workspace_id: uuid.UUID, payload: IngestIn) -> dict:
    """Store the worker's tags. Unknown categories, quotes that are not in the
    comment, and competitor tags without a name are dropped one by one."""
    ids = [it.activity_id for it in payload.items]
    if not ids:
        return {"accepted": 0, "dropped": 0, "scanned": 0, "failed": 0}
    rows = (await db.execute(text(f"""
        SELECT a.id, a.lead_id, a.user_id, a.created_at, {_COMMENT_TEXT} AS body
        FROM activities a JOIN leads l ON l.id = a.lead_id
        WHERE {_COMMENT_WHERE} AND a.id = ANY(:ids)
    """), {"wid": workspace_id, "ids": ids})).all()
    comments = {r.id: r for r in rows}

    accepted = dropped = scanned = failed = 0
    for item in payload.items:
        c = comments.get(item.activity_id)
        if c is None:  # not a comment of this workspace — ignore silently
            continue
        if item.failed:
            await _mark(db, workspace_id, c.id, "failed")
            failed += 1
            continue
        await db.execute(delete(CommentInsight).where(CommentInsight.activity_id == c.id))
        seen: set[tuple[str, str | None]] = set()
        for tag in item.tags:
            category = (tag.category or "").strip()
            competitor = normalize_competitor(tag.competitor) if category == "competitor" else None
            quote = " ".join((tag.quote or "").split())
            ok = (
                category in CATEGORIES
                and len(quote) <= 300
                and quote_in_comment(quote, scrub(c.body))
                and (category != "competitor" or competitor)
                and (category, competitor) not in seen
            )
            if not ok:
                dropped += 1
                continue
            seen.add((category, competitor))
            db.add(CommentInsight(
                workspace_id=workspace_id, activity_id=c.id, lead_id=c.lead_id,
                author_id=c.user_id, category=category, competitor=competitor,
                quote=quote, comment_at=c.created_at,
            ))
            accepted += 1
        await _mark(db, workspace_id, c.id, "done")
        scanned += 1
    await db.flush()
    return {"accepted": accepted, "dropped": dropped, "scanned": scanned, "failed": failed}


async def _mark(db: AsyncSession, workspace_id: uuid.UUID, activity_id: uuid.UUID, status: str) -> None:
    stmt = pg_insert(CommentInsightScan).values(
        activity_id=activity_id, workspace_id=workspace_id, status=status, attempts=1
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[CommentInsightScan.activity_id],
        set_={
            "status": status,
            "attempts": CommentInsightScan.attempts + 1,
            "scanned_at": text("now()"),
        },
    )
    await db.execute(stmt)


async def voice(db: AsyncSession, *, workspace_id: uuid.UUID, period: str) -> dict:
    """Tags per category over the last 7 or 30 days vs the same span before."""
    days = 30 if period == "month" else 7
    now = datetime.now(timezone.utc)
    cur_from = now - timedelta(days=days)
    prev_from = cur_from - timedelta(days=days)

    rows = (await db.execute(text("""
        SELECT i.category, i.competitor, i.quote, i.comment_at, i.lead_id,
               l.company_name, u.name AS author
        FROM comment_insights i
        JOIN leads l ON l.id = i.lead_id AND l.deleted_at IS NULL
        LEFT JOIN users u ON u.id = i.author_id
        WHERE i.workspace_id = :wid AND i.comment_at >= :prev_from
        ORDER BY i.comment_at DESC
    """), {"wid": workspace_id, "prev_from": prev_from})).all()

    items: dict[str, dict] = {}
    for r in rows:
        key = f"competitor:{r.competitor}" if r.category == "competitor" else r.category
        group, label = CATEGORIES[r.category] if r.category in CATEGORIES else (None, None)
        if group is None:
            continue
        it = items.setdefault(key, {
            "key": key, "group": group,
            "label": r.competitor if r.category == "competitor" else label,
            "cur": set(), "prev": set(), "quotes": [], "quoted": set(),
        })
        if r.comment_at >= cur_from:
            it["cur"].add(r.lead_id)
            if len(it["quotes"]) < QUOTES_PER_ITEM and r.lead_id not in it["quoted"]:
                it["quoted"].add(r.lead_id)
                it["quotes"].append({
                    "lead_id": r.lead_id, "company_name": r.company_name,
                    "author": r.author, "quote": r.quote, "at": r.comment_at,
                })
        else:
            it["prev"].add(r.lead_id)

    groups = []
    for g in GROUP_ORDER:
        g_items = [
            {"key": it["key"], "label": it["label"], "leads": len(it["cur"]),
             "previous": len(it["prev"]), "quotes": it["quotes"]}
            for it in items.values() if it["group"] == g and it["cur"]
        ]
        if g_items:
            g_items.sort(key=lambda x: (-x["leads"], x["label"]))
            groups.append({"group": g, "label": GROUP_LABELS[g], "items": g_items})

    lost = (await db.execute(text("""
        SELECT split_part(lost_reason, ' — ', 1) AS reason, count(*) AS n
        FROM leads
        WHERE workspace_id = :wid AND deleted_at IS NULL AND lost_at >= :cur_from
          AND COALESCE(lost_reason, '') <> ''
        GROUP BY 1 ORDER BY 2 DESC, 1
    """), {"wid": workspace_id, "cur_from": cur_from})).all()

    counts = (await db.execute(text(f"""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE s.activity_id IS NULL OR s.status <> 'done') AS pending
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        LEFT JOIN comment_insight_scans s ON s.activity_id = a.id
        WHERE {_COMMENT_WHERE} AND a.created_at >= :cur_from
    """), {"wid": workspace_id, "cur_from": cur_from})).one()

    last_scan = (await db.execute(
        select(CommentInsightScan.scanned_at)
        .where(CommentInsightScan.workspace_id == workspace_id)
        .order_by(CommentInsightScan.scanned_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    return {
        "period": "month" if days == 30 else "week",
        "days": days,
        "groups": groups,
        "lost_reasons": [{"reason": r.reason, "count": r.n} for r in lost],
        "comments_total": counts.total,
        "comments_pending": counts.pending,
        "last_scan_at": last_scan,
    }
