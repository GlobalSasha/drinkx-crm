"""«Голос клиентов»: what goes to the AI worker, what comes back, the summary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from tests.conftest import POSTGRES_AVAILABLE

from app.activity.models import Activity  # noqa: F401 — mapper config
from app.insights import services as svc
from app.insights.categories import CATEGORIES, normalize_competitor
from app.insights.schemas import IngestIn

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


# ── pure helpers ────────────────────────────────────────────────────────────

def test_scrub_cuts_phones_and_emails():
    out = svc.scrub("Звонил +7 (903) 217-94-16, пишите a.b@mail.ru, цена 470000р")
    assert "903" not in out and "mail.ru" not in out
    assert "[телефон]" in out and "[почта]" in out
    assert "470000р" in out  # price is not a phone


def test_quote_must_be_in_comment():
    comment = "Морозит, большой для него бюджет, много сомнений"
    assert svc.quote_in_comment("большой для него  бюджет", comment)
    assert svc.quote_in_comment("«Большой для него бюджет»", comment)
    assert not svc.quote_in_comment("слишком дорого", comment)
    assert not svc.quote_in_comment("бю", comment)  # too short to mean anything


def test_competitor_spellings_glue_together():
    assert normalize_competitor("Сканомат") == "Scanomat"
    assert normalize_competitor(" scanomat. ") == "Scanomat"
    assert normalize_competitor("Uvenco") == "Uvenco"
    assert normalize_competitor("Кофемания Про") == "Кофемания Про"
    assert normalize_competitor("  ") is None


def test_categories_are_grouped():
    assert {g for g, _ in CATEGORIES.values()} == {"objection", "question", "interest", "competitor", "contact"}


# ── DB-backed ───────────────────────────────────────────────────────────────

async def _lead(db, workspace, user, name="Кофейня", deleted=False):
    from app.leads.models import Lead
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace.id, name="P", type="sales", position=0)
    db.add(p)
    await db.flush()
    st = Stage(pipeline_id=p.id, name="Новый", position=0, color="#ccc", rot_days=14)
    db.add(st)
    await db.flush()
    lead = Lead(workspace_id=workspace.id, company_name=name, pipeline_id=p.id, stage_id=st.id,
                assignment_status="assigned", assigned_to=user.id,
                deleted_at=datetime.now(timezone.utc) if deleted else None)
    db.add(lead)
    await db.flush()
    return lead


async def _comment(db, lead, user, body, *, days_ago=1, type_="comment", by_user=True):
    a = Activity(lead_id=lead.id, workspace_id=lead.workspace_id,
                 user_id=user.id if by_user else None, type=type_, body=body,
                 payload_json={}, created_at=datetime.now(timezone.utc) - timedelta(days=days_ago))
    db.add(a)
    await db.flush()
    return a


@skip_no_pg
async def test_pending_gives_only_fresh_manager_comments(db, workspace, user):
    lead = await _lead(db, workspace, user)
    gone = await _lead(db, workspace, user, "Удалён", deleted=True)
    ok = await _comment(db, lead, user, "Дорого, звоните +7 903 111 22 33")
    await _comment(db, lead, user, "старый", days_ago=40)
    await _comment(db, lead, user, "авто", by_user=False)
    await _comment(db, lead, user, "задача", type_="task")
    await _comment(db, gone, user, "на удалённом")

    out = await svc.pending_comments(db, workspace_id=workspace.id)
    assert [c["activity_id"] for c in out] == [ok.id]
    assert "111" not in out[0]["text"] and "[телефон]" in out[0]["text"]


@skip_no_pg
async def test_ingest_keeps_only_checked_tags_and_marks_scanned(db, workspace, user):
    lead = await _lead(db, workspace, user)
    c = await _comment(db, lead, user, "Ответил что отложил, большой для него бюджет. Смотрел Сканомат.")

    res = await svc.ingest(db, workspace_id=workspace.id, payload=IngestIn(items=[{
        "activity_id": c.id,
        "tags": [
            {"category": "price", "quote": "большой для него бюджет"},
            {"category": "not_now", "quote": "отложил"},
            {"category": "competitor", "quote": "Смотрел Сканомат", "competitor": "Сканомат"},
            {"category": "price", "quote": "большой для него бюджет"},       # duplicate
            {"category": "made_up", "quote": "отложил"},                      # unknown category
            {"category": "leasing", "quote": "хочет в лизинг"},               # not in the comment
            {"category": "competitor", "quote": "Смотрел Сканомат"},          # no name
        ],
    }]))
    assert res == {"accepted": 3, "dropped": 4, "scanned": 1, "failed": 0}
    assert await svc.pending_comments(db, workspace_id=workspace.id) == []

    # Re-sending the same comment replaces its tags instead of stacking them.
    await svc.ingest(db, workspace_id=workspace.id, payload=IngestIn(items=[{
        "activity_id": c.id, "tags": [{"category": "price", "quote": "большой для него бюджет"}],
    }]))
    v = await svc.voice(db, workspace_id=workspace.id, period="week")
    keys = {it["key"] for g in v["groups"] for it in g["items"]}
    assert keys == {"price"}


@skip_no_pg
async def test_failed_comment_is_retried_three_times_then_left(db, workspace, user):
    lead = await _lead(db, workspace, user)
    c = await _comment(db, lead, user, "что-то непонятное")
    for _ in range(svc.MAX_ATTEMPTS):
        assert [x["activity_id"] for x in await svc.pending_comments(db, workspace_id=workspace.id)] == [c.id]
        await svc.ingest(db, workspace_id=workspace.id,
                         payload=IngestIn(items=[{"activity_id": c.id, "failed": True}]))
    assert await svc.pending_comments(db, workspace_id=workspace.id) == []


@skip_no_pg
async def test_ingest_ignores_comments_of_another_workspace(db, workspace, user):
    from app.auth.models import Workspace

    other = Workspace(name="Other", plan="pro", sprint_capacity_per_week=20)
    db.add(other)
    await db.flush()
    lead = await _lead(db, workspace, user)
    c = await _comment(db, lead, user, "дорого")
    res = await svc.ingest(db, workspace_id=other.id, payload=IngestIn(items=[{
        "activity_id": c.id, "tags": [{"category": "price", "quote": "дорого"}],
    }]))
    assert res["accepted"] == 0 and res["scanned"] == 0


@skip_no_pg
async def test_voice_counts_leads_per_period_with_quotes_and_lost_reasons(db, workspace, user):
    a = await _lead(db, workspace, user, "Кофейня А")
    b = await _lead(db, workspace, user, "Кофейня Б")
    old = await _lead(db, workspace, user, "Прошлая")
    c1 = await _comment(db, a, user, "цена кусается", days_ago=1)
    c2 = await _comment(db, a, user, "опять про цену, кусается", days_ago=2)
    c3 = await _comment(db, b, user, "дорого, нужен лизинг", days_ago=3)
    c4 = await _comment(db, old, user, "дорого было", days_ago=10)
    await svc.ingest(db, workspace_id=workspace.id, payload=IngestIn(items=[
        {"activity_id": c1.id, "tags": [{"category": "price", "quote": "цена кусается"}]},
        {"activity_id": c2.id, "tags": [{"category": "price", "quote": "кусается"}]},
        {"activity_id": c3.id, "tags": [{"category": "price", "quote": "дорого"},
                                       {"category": "leasing", "quote": "нужен лизинг"}]},
        {"activity_id": c4.id, "tags": [{"category": "price", "quote": "дорого было"}]},
    ]))
    a.lost_at = datetime.now(timezone.utc) - timedelta(days=1)
    a.lost_reason = "Не устроила цена — сравнивал с вендингом"
    await db.flush()

    v = await svc.voice(db, workspace_id=workspace.id, period="week")
    objections = next(g for g in v["groups"] if g["group"] == "objection")
    price = next(i for i in objections["items"] if i["key"] == "price")
    assert price["leads"] == 2          # А counted once despite two comments
    assert price["previous"] == 1       # «Прошлая», 10 days ago
    assert [q["company_name"] for q in price["quotes"]] == ["Кофейня А", "Кофейня Б"]  # newest first, one per lead
    assert objections["items"][0]["key"] == "price"  # most leads first
    assert v["lost_reasons"] == [{"reason": "Не устроила цена", "count": 1}]
    assert v["comments_total"] == 3 and v["comments_pending"] == 0
    assert v["last_scan_at"] is not None


@skip_no_pg
async def test_worker_key_needs_insights_scope(db, workspace):
    from app.external import keys
    from app.external.dependencies import resolve_service_key
    from app.external.models import ServiceApiKey

    token, key_hash = keys.generate_key()
    db.add(ServiceApiKey(workspace_id=workspace.id, name="OS", key_hash=key_hash, scopes=["read:core"]))
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await resolve_service_key(db, token, scope="write:insights")
    assert exc.value.status_code == 403
