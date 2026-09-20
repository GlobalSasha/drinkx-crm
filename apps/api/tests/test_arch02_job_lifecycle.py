"""ARCH-02, фаза 2 — QA-разведка жизненного цикла фоновых задач.

Синтетические данные, база `drinkx_ci3`, никакого настоящего Celery /
Redis / AI / SMTP — только записывающие заглушки (тот же приём, что в
`test_sec06_import_happy_path.py` и `test_sec04_base_update_access.py`:
воркер вызывается явно на тестовой сессии, `celery_app.send_task`
подменяется списком).

Каждый тест фиксирует ФАКТИЧЕСКОЕ поведение кода на сегодня. Там, где
`TRANSACTION_AND_JOB_REVIEW.md` называет это дефектом, комментарий над
assert'ом говорит «ожидаемое по контракту: …» — assert при этом всё
равно проверяет то, что код делает сейчас, а не то, что должен.

Источники сценариев: ARCH-02/TRANSACTION_AND_JOB_REVIEW.md (§6, Q-1…Q-27),
ARCH-02/JOB_STATE_TABLES.md. Из приоритетного списка фазы 2 здесь взяты
первые шесть: Q-1, Q-9, Q-10, Q-7, Q-12, Q-3.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401 — настраивает мапперы SQLAlchemy
import app.utm.models  # noqa: F401 — worker импорта пишет в справочники UTM
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


# ===========================================================================
# Общая обвязка (повторяет test_sec06_import_happy_path.py / test_sec04_*)
# ===========================================================================

async def _workspace(db, name: str):
    from app.auth.models import Workspace

    ws = Workspace(name=name, plan="pro", sprint_capacity_per_week=20)
    db.add(ws)
    await db.flush()
    return ws


async def _user(db, workspace_id, name: str, role: str = "manager"):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


async def _default_pipeline(db, workspace):
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace.id, name="Основная", type="sales", position=0)
    db.add(p)
    await db.flush()
    s = Stage(pipeline_id=p.id, name="Новые", position=0, color="#aabbcc", rot_days=14)
    db.add(s)
    await db.flush()
    workspace.default_pipeline_id = p.id
    await db.flush()
    return p, s


async def _lead(db, workspace_id, name, owner_id=None, company_id=None, email=None):
    from app.leads import repositories as repo

    data: dict = dict(company_name=name)
    if company_id is not None:
        data["company_id"] = company_id
    if email is not None:
        data["email"] = email
    return await repo.create_lead(
        db, workspace_id, data,
        assigned_to=owner_id,
        assignment_status="assigned" if owner_id else "pool",
    )


async def _company(db, workspace_id, name: str, **fields):
    from app.companies.models import Company

    co = Company(workspace_id=workspace_id, name=name, normalized_name=name.lower(), **fields)
    db.add(co)
    await db.flush()
    return co


async def call(db, actor, method, path, body=None, files=None, raise_errors=True):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=raise_errors)
        async with AsyncClient(transport=transport, base_url="http://test") as cl:
            kwargs: dict = {}
            if files is not None:
                kwargs["files"] = files
            elif method in ("POST", "PATCH", "PUT"):
                kwargs["json"] = body if body is not None else {}
            return await cl.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def no_queue(monkeypatch):
    """Очередь — записывающая заглушка: ни одного реального вызова Celery."""
    from app.scheduled.celery_app import celery_app

    sent: list[tuple] = []
    monkeypatch.setattr(
        celery_app, "send_task", lambda name, *a, **kw: sent.append((name, a, kw))
    )
    return sent


async def run_import_worker(db, job_id):
    """Настоящий `_run_bulk_import` на тестовой сессии (как в SEC-06)."""
    from app.scheduled import jobs as jobs_mod

    class _Holder:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *exc):
            return False

    class _Engine:
        async def dispose(self_inner):
            return None

    orig = jobs_mod._build_task_engine_and_factory
    jobs_mod._build_task_engine_and_factory = lambda: (_Engine(), lambda: _Holder())
    try:
        return await jobs_mod._run_bulk_import(job_id)
    finally:
        jobs_mod._build_task_engine_and_factory = orig


async def _fresh_session():
    """Отдельная сессия, независимая от той, где сидит worker/тест —
    нужна, чтобы по-настоящему сымитировать два параллельных ядра на
    одной БД, а не два вызова в одной и той же сессии/транзакции."""
    from tests.conftest import _test_session_factory

    return _test_session_factory()


# ===========================================================================
# Q-1 (P1, ARCH-JOB-01 — ожидается нарушение). Повтор bulk_import_run
# на задании в running заводит карточки второй раз.
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_q1_repeat_bulk_import_on_running_duplicates_leads(db):
    from sqlalchemy import select

    from app.import_export.models import ImportJob
    from app.leads.models import Lead

    ws = await _workspace(db, "Q1")
    await _default_pipeline(db, ws)
    owner = await _user(db, ws.id, "Owner")
    await db.commit()

    job = ImportJob(
        workspace_id=ws.id,
        user_id=owner.id,
        status="running",
        format="csv",
        source_filename="q1.csv",
        total_rows=2,
        processed=2,
        succeeded=2,
        failed=0,
        diff_json={
            "mapped_rows": [
                {"company_name": "Ромашка"},
                {"company_name": "Василёк"},
            ]
        },
    )
    db.add(job)
    await db.commit()

    # Задача дёрнута второй раз (человек нажал «применить» ещё раз,
    # либо это повторная доставка того же сообщения) — охранник
    # (`jobs.py:1118-1121`) пускает статус `running`.
    result = await run_import_worker(db, job.id)

    # Ожидаемое по контракту: повторный запуск должен либо ничего не
    # делать (задание уже применено), либо продолжить с того места,
    # где остановился курсор. Кода, который бы это обеспечивал, нет —
    # F-7: строки применяются заново, счётчики наращиваются поверх.
    leads = (
        await db.execute(
            select(Lead.company_name).where(
                Lead.workspace_id == ws.id,
                Lead.company_name.in_(["Ромашка", "Василёк"]),
            )
        )
    ).scalars().all()
    assert sorted(leads) == ["Василёк", "Ромашка"], "повтор не завёл карточки второй раз"

    await db.refresh(job)
    assert (job.succeeded, job.processed) == (4, 4), "счётчики не наросли поверх старых"
    assert job.status == "succeeded"
    # Возврат воркера — это уже наросшее состояние job (кумулятивное), а
    # не «сколько сделала именно эта попытка»: тот же симптом F-7 виден
    # и в форме ответа задачи, не только в таблице.
    assert result["succeeded"] == 4


@skip_no_pg
@pytest.mark.asyncio
async def test_q1_control_repeat_on_terminal_status_is_skipped(db):
    """Контроль к Q-1: охранник действительно останавливает повтор,
    когда статус уже терминальный (`succeeded`) — это не F-7, это
    работающая часть охранника."""
    from sqlalchemy import select

    from app.import_export.models import ImportJob
    from app.leads.models import Lead

    ws = await _workspace(db, "Q1-control")
    await _default_pipeline(db, ws)
    owner = await _user(db, ws.id, "Owner")
    await db.commit()

    job = ImportJob(
        workspace_id=ws.id,
        user_id=owner.id,
        status="succeeded",
        format="csv",
        source_filename="q1c.csv",
        total_rows=1,
        processed=1,
        succeeded=1,
        failed=0,
        diff_json={"mapped_rows": [{"company_name": "Одуванчик"}]},
    )
    db.add(job)
    await db.commit()

    result = await run_import_worker(db, job.id)
    assert result == {"job": "bulk_import_run", "skipped": "succeeded"}

    leads = (
        await db.execute(
            select(Lead.company_name).where(Lead.company_name == "Одуванчик")
        )
    ).scalars().all()
    assert leads == [], "терминальный статус должен останавливать повтор — и останавливает"


# ===========================================================================
# Q-9 (P1, ARCH-JOB-01/04). Наложение двух тиков `execute_due_step_runs`
# на один и тот же шаг.
# БЫЛО: выборка без блокировки → оба тика брали строку, письмо уходило
# дважды. СТАЛО (S-3): `FOR UPDATE SKIP LOCKED` — второй тик строку не
# видит, письмо одно.
# ===========================================================================

async def _automation_with_email_step(db, ws, lead):
    from app.automation_builder.models import Automation, AutomationRun, AutomationStepRun
    from app.template.models import MessageTemplate

    template = MessageTemplate(
        workspace_id=ws.id, name="Follow-up", channel="email", text="Здравствуйте, {{company_name}}",
    )
    db.add(template)
    await db.flush()

    automation = Automation(
        workspace_id=ws.id, name="Q9", trigger="stage_change",
        action_type="send_template", action_config_json={"template_id": str(template.id)},
    )
    db.add(automation)
    await db.flush()

    run = AutomationRun(automation_id=automation.id, lead_id=lead.id, status="success")
    db.add(run)
    await db.flush()

    step_run = AutomationStepRun(
        automation_run_id=run.id,
        lead_id=lead.id,
        step_index=1,
        step_json={"type": "send_template", "config": {"template_id": str(template.id)}},
        scheduled_at=datetime.now(tz=timezone.utc) - timedelta(minutes=1),
        executed_at=None,
        status="pending",
        attempt_count=0,
    )
    db.add(step_run)
    await db.flush()
    return step_run


@skip_no_pg
@pytest.mark.asyncio
async def test_q9_overlapping_scheduler_ticks_send_second_email(db, monkeypatch):
    from sqlalchemy import select

    from app.activity.models import Activity
    from app.automation_builder import services as automation_svc

    ws = await _workspace(db, "Q9")
    await _default_pipeline(db, ws)
    lead = await _lead(db, ws.id, "Компания Q9", email="lead-q9@example.com")
    step_run = await _automation_with_email_step(db, ws, lead)
    await db.commit()

    sent_emails: list[str] = []

    async def _fake_send_email(*, to, subject, body):
        sent_emails.append(to)
        return True

    monkeypatch.setattr(
        "app.automation_builder.dispatch.send_email", _fake_send_email
    )

    other = await _fresh_session()
    try:
        # `list_due_step_runs` берёт `FOR UPDATE SKIP LOCKED` (S-3).
        # Нужен настоящий параллелизм: последовательные вызовы ничего не
        # докажут — вторая сессия просто увидит уже исполненную строку.
        # `asyncio.gather` даёт обеим сессиям сделать SELECT одновременно —
        # ровно та гонка, которую блокировка и должна гасить.
        result_a, result_b = await asyncio.gather(
            automation_svc.execute_due_step_runs(db),
            automation_svc.execute_due_step_runs(other),
        )
    finally:
        await other.close()

    # было: (1, 1) — оба тика отрабатывали шаг. Стало: строку берёт ровно
    # один тик, второй пропускает её по SKIP LOCKED. Какой именно из двух
    # успеет первым — дело планировщика asyncio, поэтому сравниваем пару
    # без учёта порядка.
    assert sorted([result_a["fired"], result_b["fired"]]) == [0, 1], (
        "шаг исполняет ровно один тик из двух"
    )

    await db.refresh(step_run)
    assert step_run.status == "success"

    # Два отдельных Activity(type='comment') с одним и тем же письмом —
    # видимый пользователю дубль.
    activities = (
        await db.execute(
            select(Activity).where(Activity.lead_id == lead.id, Activity.type == "comment")
        )
    ).scalars().all()
    # было: 2 (дубль в ленте) и 2 письма.
    assert len(activities) == 1, "одно письмо — одна Activity"
    assert sent_emails == ["lead-q9@example.com"], "SMTP-заглушка звонит один раз"


# ===========================================================================
# Q-10 (P1, ARCH-JOB-01). Наложение двух тиков followup-напоминалок.
# БЫЛО: выборка без блокировки → второй тик заводил вторую напоминалку.
# СТАЛО (S-3): `FOR UPDATE SKIP LOCKED` — followup обрабатывает один тик.
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_q10_overlapping_followup_dispatch_is_serialized(db):
    from sqlalchemy import select

    from app.activity.models import Activity, ActivityType
    from app.followups.dispatcher import run_followup_dispatch
    from app.followups.models import Followup
    from app.notifications.models import Notification

    ws = await _workspace(db, "Q10")
    await _default_pipeline(db, ws)
    owner = await _user(db, ws.id, "Owner")
    lead = await _lead(db, ws.id, "Компания Q10", owner_id=owner.id)
    await db.commit()

    followup = Followup(
        lead_id=lead.id,
        name="Перезвонить",
        due_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        status="pending",
        dispatched_at=None,
    )
    db.add(followup)
    await db.commit()

    other = await _fresh_session()
    try:
        # `run_followup_dispatch` — одна транзакция на весь тик, теперь
        # с `FOR UPDATE SKIP LOCKED` (S-3). Как и в Q-9, нужен настоящий
        # параллелизм: `asyncio.gather` сталкивает обе сессии на одной и
        # той же строке.
        created_a, created_b = await asyncio.gather(
            run_followup_dispatch(db), run_followup_dispatch(other)
        )
    finally:
        await other.close()

    # было: (1, 1) — вторая напоминалка на тот же followup.
    assert sorted([created_a, created_b]) == [0, 1], (
        "followup обрабатывает ровно один тик из двух"
    )

    reminders = (
        await db.execute(
            select(Activity).where(
                Activity.lead_id == lead.id, Activity.type == ActivityType.reminder.value
            )
        )
    ).scalars().all()
    # было: 2.
    assert len(reminders) == 1, "один followup — одно напоминание"

    notifications = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == owner.id, Notification.lead_id == lead.id
            )
        )
    ).scalars().all()
    # Раньше уведомление не задваивалось случайно — общим часовым
    # dedup-фильтром `notifications/services.py::_has_recent_same_kind`.
    # Теперь второго вызова просто не происходит, и одно уведомление —
    # следствие блокировки, а не совпадения.
    assert len(notifications) == 1, "один followup — одно уведомление"


# ===========================================================================
# Q-7 (P1, ARCH-JOB-02). Зомби-строки enrichment_runs в running занимают
# потолок конкурентности пространства — новый запуск получает 429.
# БЫЛО: освободить место мог только ленивый сторож в `get_latest_run`, то
# есть лишь когда кто-то откроет карточку именно зомби-лида; беат-прохода
# не было вовсе. СТАЛО (S-2): `expire_stuck_runs` гасит все просроченные
# строки разом, потолок освобождается без участия человека.
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_q7_zombie_enrichment_runs_exhaust_workspace_concurrency(db):
    from app.config import get_settings
    from app.enrichment.models import EnrichmentRun
    from app.enrichment.services import (
        EnrichmentConcurrencyLimit,
        expire_stuck_runs,
        trigger_enrichment,
    )

    ws = await _workspace(db, "Q7")
    await _default_pipeline(db, ws)
    owner = await _user(db, ws.id, "Owner")
    limit = get_settings().ai_max_parallel_jobs

    old_started = datetime.now(tz=timezone.utc) - timedelta(days=3)
    for i in range(limit):
        lead = await _lead(db, ws.id, f"Зомби-лид {i}")
        run = EnrichmentRun(
            lead_id=lead.id, user_id=owner.id, status="running", started_at=old_started,
        )
        db.add(run)
    await db.commit()

    # Новый лид, к которому никто не обращался через get_latest_run —
    # ленивый сторож (F-2) ни разу не сработал ни на одну зомби-строку.
    fresh_lead = await _lead(db, ws.id, "Новый лид")
    await db.commit()

    with pytest.raises(EnrichmentConcurrencyLimit):
        # Ожидаемое по контракту: сторож должен освобождать место сам
        # (beat-задача из S-2), а не только когда кто-то откроет карточку
        # именно зомби-лида. Сейчас — 429 на всё пространство.
        await trigger_enrichment(
            db, workspace_id=ws.id, user_id=owner.id, lead_id=fresh_lead.id,
        )

    from sqlalchemy import func, select

    count_running = select(func.count(EnrichmentRun.id)).where(
        EnrichmentRun.status == "running"
    )
    assert (await db.execute(count_running)).scalar_one() == limit, (
        "до прохода сторожа зомби-строки остаются running"
    )

    # Беат-сторож S-2: тот же код, что зовёт задача
    # `expire_stuck_enrichment_runs`, только на тестовой сессии.
    expired = await expire_stuck_runs(db)
    await db.commit()
    assert expired == limit, "сторож гасит все просроченные строки за один проход"
    assert (await db.execute(count_running)).scalar_one() == 0

    # Потолок освобождён. Проверяем именно его: пройти `trigger_enrichment`
    # целиком здесь нельзя — следующий за конкурентностью охранник смотрит
    # дневной бюджет в Redis, а Redis в тестовой среде не поднят и fail-closed
    # даёт EnrichmentBudgetExceeded независимо от нашей правки.
    from app.enrichment.concurrency import (
        count_running_for_workspace,
        is_at_concurrency_limit,
    )

    assert await count_running_for_workspace(db, ws.id) == 0
    assert await is_at_concurrency_limit(db, ws.id) is False


# ===========================================================================
# Q-12 (P1, ARCH-JOB-01). Повторный base_update_apply на одном и том же
# решении без терминального состояния заводит вторую сущность.
#
# ОТКЛОНЕНИЕ ОТ ДОКУМЕНТА: Q-12 в TRANSACTION_AND_JOB_REVIEW.md описан на
# `R_ADD_SEPARATE`/`add_contact` (дубль контакта). При разведке этот путь
# оказался сломан ИНАЧЕ и раньше, чем предполагал документ — см. отдельный
# тест `test_q12_bonus_add_contact_op_is_broken_by_field_name_mismatch`
# ниже: `_execute_op` вообще не может создать контакт (падает на разборе
# аргументов, а не на дубле), так что F-8 в этой ветке не воспроизводится
# в заявленном виде. F-8 (решение без терминального состояния) полностью
# воспроизводима на соседней ветке того же `_decide_apply` — `C_LEAD_TARGET`
# + `R_KEEP` → `create_new_lead` (`services.py:588-619`), которая тем же
# способом не меняет `cf.status` при успехе. Это тот же дефект A-3, что и
# в документе, показанный на работающем пути.
# ===========================================================================

async def _base_update_job(db, ws, user, status):
    from app.base_update.models import IngestJob

    job = IngestJob(
        workspace_id=ws.id, user_id=user.id, status=status,
        file_count=1, source_filenames=["карточка.md"], stats_json={},
    )
    db.add(job)
    await db.flush()
    return job


@skip_no_pg
@pytest.mark.asyncio
async def test_q12_repeat_base_update_apply_duplicates_new_lead(db):
    from sqlalchemy import func, select

    from app.base_update import constants as c
    from app.base_update.models import IngestConflict, IngestRecord
    from app.base_update.orchestrator import run_apply_resolutions
    from app.leads.models import Lead

    ws = await _workspace(db, "Q12")
    await _default_pipeline(db, ws)
    admin = await _user(db, ws.id, "Admin", "admin")
    co = await _company(db, ws.id, "Компания Q12")
    await db.commit()

    job = await _base_update_job(db, ws, admin, c.JOB_READY)
    record = IngestRecord(
        ingest_job_id=job.id, company_name="Компания Q12", normalized_name="компания q12",
        extracted_json={"company": {"name": "Компания Q12"}},
        match_company_id=co.id, match_lead_id=None, confidence=0.9,
    )
    db.add(record)
    await db.flush()

    # C_LEAD_TARGET + R_KEEP → op "create_new_lead" (`_decide_apply`,
    # services.py:494-498): «карточки под этой компанией нет, завести
    # новую», то же семейство риска, что и `add_separate` для контакта.
    conflict = IngestConflict(
        ingest_job_id=job.id, ingest_record_id=record.id,
        type=c.C_LEAD_TARGET, target_kind=c.TK_LEAD, field_name=None,
        base_value=None, incoming_value=None, candidates_json=None,
        status=c.CONFLICT_RESOLVED, resolution=c.R_KEEP, resolved_value=None,
    )
    db.add(conflict)
    await db.commit()

    count_stmt = select(func.count(Lead.id)).where(
        Lead.workspace_id == ws.id, Lead.company_name == "Компания Q12", Lead.source == "base_update",
    )

    # Первый прогон worker'а — создаёт лид.
    await run_apply_resolutions(db=db, job_id=job.id)
    assert (await db.execute(count_stmt)).scalar_one() == 1

    await db.refresh(conflict)
    # F-8: успешно применённое решение остаётся `resolved` — терминального
    # состояния «применено» у конфликта нет ни у одной ветки `_decide_apply`.
    assert conflict.status == c.CONFLICT_RESOLVED

    # Второй прогон (человек нажал «применить» ещё раз, или это повторная
    # доставка той же задачи) — worker снова видит тот же CONFLICT_RESOLVED.
    await run_apply_resolutions(db=db, job_id=job.id)

    # Ожидаемое по контракту: повтор не должен заводить вторую карточку —
    # у решения должно быть терминальное состояние (A-3). Сейчас заводит.
    assert (await db.execute(count_stmt)).scalar_one() == 2, (
        "повтор применения решения не должен заводить дубликат — но заводит"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_q12_bonus_add_contact_op_maps_contact_field_names(db):
    """Побочная находка разведки Q-12 (ARCH-DELTA-001), не из документа фазы 1.

    БЫЛО: `_execute_op`'s `add_contact` собирал аргументы `create_contact`
    как `{"telegram": …, "linkedin": …}`, а модель `Contact` называет эти
    поля `telegram_url`/`linkedin_url` (`app/contacts/models.py:63-64`).
    ЛЮБОЙ `R_ADD_SEPARATE` по контакту падал с `TypeError: 'telegram' is
    an invalid keyword argument for Contact`, конфликт возвращался в
    `open`, контактов создавалось 0.

    СТАЛО: `CONTACT_FIELD_ALIASES` переводит имена извлечённой карточки в
    имена колонок — контакт создаётся, запись без ошибки, статус конфликта
    остаётся `resolved` (терминального состояния у применённого решения
    по-прежнему нет — это F-8/A-3, отдельный вопрос).
    """
    from sqlalchemy import func, select

    from app.base_update import constants as c
    from app.base_update.models import IngestConflict, IngestRecord
    from app.base_update.orchestrator import run_apply_resolutions
    from app.contacts.models import Contact

    ws = await _workspace(db, "Q12-bonus")
    await _default_pipeline(db, ws)
    admin = await _user(db, ws.id, "Admin", "admin")
    co = await _company(db, ws.id, "Компания Q12b")
    lead = await _lead(db, ws.id, "Лид Q12b", company_id=co.id)
    await db.commit()

    job = await _base_update_job(db, ws, admin, c.JOB_READY)
    record = IngestRecord(
        ingest_job_id=job.id, company_name="Компания Q12b", normalized_name="компания q12b",
        extracted_json={"company": {"name": "Компания Q12b"}},
        match_company_id=co.id, match_lead_id=lead.id, confidence=0.9,
    )
    db.add(record)
    await db.flush()

    contact_payload = {
        "name": "Новый ЛПР", "title": "CEO", "role_type": "economic_buyer",
        "email": "new-lpr@example.com", "phone": None, "telegram": None, "linkedin": None,
    }
    conflict = IngestConflict(
        ingest_job_id=job.id, ingest_record_id=record.id,
        type=c.C_CONTACT_MISMATCH, target_kind=c.TK_CONTACT, field_name="name",
        base_value=None, incoming_value=None, candidates_json=[contact_payload],
        status=c.CONFLICT_RESOLVED, resolution=c.R_ADD_SEPARATE, resolved_value=None,
    )
    db.add(conflict)
    await db.commit()

    await run_apply_resolutions(db=db, job_id=job.id)

    # было: 0 (падало на TypeError) → стало: 1 созданный контакт.
    count_stmt = select(func.count(Contact.id)).where(Contact.lead_id == lead.id)
    assert (await db.execute(count_stmt)).scalar_one() == 1, "add_contact создаёт отдельный контакт"

    created = (
        await db.execute(select(Contact).where(Contact.lead_id == lead.id))
    ).scalars().one()
    assert created.name == "Новый ЛПР"
    assert created.email == "new-lpr@example.com"
    # Поля-псевдонимы доезжают до колонок модели (в этом payload они None,
    # но важно, что аргумент принят, а не отвергнут конструктором).
    assert created.telegram_url is None
    assert created.linkedin_url is None
    assert created.source == "base_update"

    await db.refresh(record)
    # было: "add_contact failed: 'telegram' is an invalid keyword argument…"
    assert record.error is None

    await db.refresh(conflict)
    # было: CONFLICT_OPEN (откат после неудачи) → стало: успех статус не трогает.
    assert conflict.status == c.CONFLICT_RESOLVED


# ===========================================================================
# Q-3 (P2, ARCH-JOB-02 — ожидается нарушение). Обрыв bulk_import_run
# посередине оставляет задание в `running` навсегда и без пути назад.
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_q3_bulk_import_interrupted_mid_run_leaves_job_stuck(db, no_queue):
    from sqlalchemy import select

    from app.import_export import services as import_svc
    from app.import_export import validators as validators_mod
    from app.import_export.models import ImportJob
    from app.leads.models import Lead

    ws = await _workspace(db, "Q3")
    await _default_pipeline(db, ws)
    owner = await _user(db, ws.id, "Owner")
    await db.commit()

    job = ImportJob(
        workspace_id=ws.id, user_id=owner.id, status="previewed", format="csv",
        source_filename="q3.csv", total_rows=4, processed=0, succeeded=0, failed=0,
        diff_json={
            "mapped_rows": [
                {"company_name": "Первая"},
                {"company_name": "Вторая — тут обрыв"},
                {"company_name": "Третья"},
                {"company_name": "Четвёртая"},
            ]
        },
    )
    db.add(job)
    await db.commit()

    # `/apply` в реальности переводит в running ДО постановки задачи —
    # воспроизводим тот же порядок напрямую.
    await import_svc.request_apply(db, job_id=job.id, actor=owner)
    assert no_queue, "apply должен был поставить задачу"

    real_validate_row = validators_mod.validate_row
    call_count = {"n": 0}

    def _validate_row_that_dies_on_second_row(row):
        call_count["n"] += 1
        if call_count["n"] == 2:
            # BaseException, а не Exception — мимо `except Exception` в
            # `_run_bulk_import`, как SIGKILL/`SoftTimeLimitExceeded`
            # проходит мимо прикладного `try`. Сценарий из документа:
            # «ядро на 2-й из 4 строк бросает исключение мимо except Exception».
            raise KeyboardInterrupt("симуляция жёсткого обрыва")
        return real_validate_row(row)

    # `_run_bulk_import` делает `from app.import_export.validators import
    # validate_row` ЛОКАЛЬНО при каждом вызове — патчить нужно исходный
    # модуль, а не `app.scheduled.jobs` (там своего атрибута нет).
    validators_mod.validate_row = _validate_row_that_dies_on_second_row
    try:
        with pytest.raises(KeyboardInterrupt):
            await run_import_worker(db, job.id)
    finally:
        validators_mod.validate_row = real_validate_row

    await db.refresh(job)
    # Первая строка прошла целиком (succeeded, processed=1, commit).
    # Вторая: `validate_row` бросает мимо `except Exception` ДО того, как
    # для неё создан Lead — но `finally: job.processed += 1; commit()`
    # выполняется даже при пробросе BaseException, так что счётчик
    # обработанных строк успевает вырасти до 2, а `succeeded`/`failed`
    # для второй строки — нет (это честная фиксация того, что есть, а
    # не подгонка): processed опережает succeeded+failed после обрыва.
    assert job.processed == 2
    assert job.succeeded == 1
    assert job.failed == 0
    # Ожидаемое по контракту: обрыв должен оставлять статус, который
    # можно продолжить или перезапустить. Сейчас — тупик: status
    # остаётся тем, что выставил `/apply` (running), терминальный
    # переход (`succeeded`/`failed`) в конце функции не выполнился.
    assert job.status == "running", "задание зависло в running — обрыв не оставляет честный статус"

    created = (
        await db.execute(
            select(Lead.company_name).where(Lead.workspace_id == ws.id)
        )
    ).scalars().all()
    assert created == ["Первая"], "только первая строка успела примениться"

    # Из UI выйти из этого состояния нельзя: `/apply` требует `previewed`.
    r = await call(db, owner, "POST", f"/api/import/jobs/{job.id}/apply", raise_errors=False)
    assert r.status_code == 409, (
        "ожидаемое по контракту: должен быть путь возобновления/перезапуска — "
        "сейчас 409 и тупик (F-1/F-7)"
    )
