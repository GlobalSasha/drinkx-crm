"""Synthetic data for the UX-01/02/03 local walkthrough (leads/tasks/import/forecast).

Idempotent: re-running upserts by deterministic markers (user email, lead
company_name+workspace, task subject+lead/workspace) instead of inserting
duplicates. Safe to re-run after `alembic upgrade head` on a fresh DB or on
top of a previous seed run.

Only ever targets a disposable database - refuses to run against anything
not on the allowlist via `scripts.db_safety.assert_disposable` (same guard
the test suite uses). This DB is DIFFERENT from `drinkx_test`/`drinkx_ci`,
so it must be added explicitly:

    export TEST_DB_ALLOWED_NAMES=drinkx_ux
    export DATABASE_URL=postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_ux
    apps/api/.venv/bin/python -m scripts.seed_ux_synthetic   # from apps/api/

Creates:
  - 2 workspaces ("DrinkX UX Sandbox", "DrinkX UX Sandbox 2" - cross-workspace
    isolation target). NOTE: production sign-in enforces a single shared
    workspace (see app/auth/services.py); this script writes directly via
    the ORM and does not go through that flow, so a second workspace here
    is a seed-only construct for testing isolation at the API/DB layer.
  - default pipeline + 12 DEFAULT_STAGES per workspace
  - users covering admin / head / manager in workspace 1 (manager-owner +
    manager-other), plus one admin in workspace 2
  - ~60 leads in workspace 1 (assigned across managers + pool), a handful
    in workspace 2
  - ~40 tasks (activities type=task): lead-scoped + standalone, with/without
    explicit assignee, mixed due dates and done/open state
  - a sample import CSV at /tmp/ux_leads_import_sample.csv
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # apps/api on path

from scripts.db_safety import assert_disposable  # noqa: E402

import app.models_registry  # noqa: E402,F401 — populates SQLAlchemy relationship registry

from app.auth.models import User, Workspace  # noqa: E402
from app.pipelines.models import DEFAULT_STAGES, Pipeline, Stage  # noqa: E402
from app.leads.models import Lead, LeadStageHistory  # noqa: E402
from app.activity.models import Activity  # noqa: E402

random.seed(20260921)  # deterministic re-runs

CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Краснодар"]
SEGMENTS = ["retail", "horeca", "qsr", "gas_station"]
DEAL_TYPES = ["enterprise_direct", "qsr", "distributor_partner", "raw_materials", "private_small", "service_repeat"]
PRIORITIES = ["A", "B", "C", "D"]
COMPANY_WORDS = ["Кофе", "Стан", "Ритейл", "Групп", "Трейд", "Сервис", "Маркет", "Экспресс", "Плюс", "Юнион"]


def company_name(i: int, suffix: str = "") -> str:
    a = COMPANY_WORDS[i % len(COMPANY_WORDS)]
    b = COMPANY_WORDS[(i * 7 + 3) % len(COMPANY_WORDS)]
    return f"{a}{b}{suffix} №{i}"


async def get_or_create_workspace(session: AsyncSession, *, name: str) -> Workspace:
    res = await session.execute(select(Workspace).where(Workspace.name == name))
    ws = res.scalar_one_or_none()
    if ws is not None:
        return ws
    ws = Workspace(name=name, plan="free")
    session.add(ws)
    await session.flush()
    return ws


async def get_or_create_pipeline(session: AsyncSession, *, workspace: Workspace) -> Pipeline:
    res = await session.execute(
        select(Pipeline).where(Pipeline.workspace_id == workspace.id, Pipeline.name == "Новые клиенты")
    )
    pipeline = res.scalar_one_or_none()
    if pipeline is not None:
        return pipeline
    pipeline = Pipeline(workspace_id=workspace.id, name="Новые клиенты", type="sales", position=0)
    session.add(pipeline)
    await session.flush()
    for s in DEFAULT_STAGES:
        session.add(Stage(pipeline_id=pipeline.id, **s))
    await session.flush()
    workspace.default_pipeline_id = pipeline.id
    await session.flush()
    return pipeline


async def get_or_create_user(
    session: AsyncSession, *, workspace: Workspace, email: str, name: str, role: str
) -> User:
    res = await session.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if user is not None:
        user.role = role
        user.workspace_id = workspace.id
        user.onboarding_completed = True
        return user
    user = User(
        workspace_id=workspace.id,
        email=email,
        name=name,
        role=role,
        supabase_user_id=f"ux-seed-{uuid.uuid4()}",
        onboarding_completed=True,
        last_login_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create_lead(
    session: AsyncSession,
    *,
    workspace: Workspace,
    pipeline: Pipeline,
    stages: list[Stage],
    name: str,
    assigned_to: uuid.UUID | None,
    assignment_status: str,
    idx: int,
) -> Lead:
    res = await session.execute(
        select(Lead).where(Lead.workspace_id == workspace.id, Lead.company_name == name)
    )
    lead = res.scalar_one_or_none()
    if lead is not None:
        return lead

    stage = stages[idx % (len(stages) - 2)]  # keep out of the two closing stages by default
    lead = Lead(
        workspace_id=workspace.id,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        company_name=name,
        segment=SEGMENTS[idx % len(SEGMENTS)],
        city=CITIES[idx % len(CITIES)],
        email=f"contact{idx}@{name.lower().replace(' ', '').replace('№', 'n')}.example",
        phone=f"+7900{1000000 + idx:07d}",
        deal_type=DEAL_TYPES[idx % len(DEAL_TYPES)],
        commercial_model="rental" if idx % 3 == 0 else "sale",
        deal_amount=round(random.uniform(150_000, 4_500_000), 2),
        priority=PRIORITIES[idx % len(PRIORITIES)],
        source="ux_seed",
        assignment_status=assignment_status,
        assigned_to=assigned_to,
        assigned_at=datetime.now(timezone.utc) if assigned_to else None,
    )
    session.add(lead)
    await session.flush()

    session.add(
        LeadStageHistory(
            lead_id=lead.id,
            stage_id=stage.id,
            entered_at=datetime.now(timezone.utc) - timedelta(days=idx % 10),
        )
    )
    return lead


async def get_or_create_task(
    session: AsyncSession,
    *,
    workspace: Workspace,
    lead: Lead | None,
    assignee_user_id: uuid.UUID | None,
    subject: str,
    due_offset_days: int,
    done: bool,
) -> Activity:
    res = await session.execute(
        select(Activity).where(
            Activity.type == "task",
            Activity.subject == subject,
            Activity.lead_id == (lead.id if lead else None),
        )
    )
    task = res.scalar_one_or_none()
    if task is not None:
        return task

    due_at = datetime.now(timezone.utc) + timedelta(days=due_offset_days)
    task = Activity(
        lead_id=lead.id if lead else None,
        workspace_id=None if lead else workspace.id,
        assignee_user_id=assignee_user_id,
        type="task",
        subject=subject,
        body=f"Синтетическая задача UX-стенда: {subject}",
        task_due_at=due_at,
        task_done=done,
        task_completed_at=(due_at - timedelta(hours=2)) if done else None,
    )
    session.add(task)
    await session.flush()
    return task


async def seed_workspace_1(session: AsyncSession) -> dict:
    ws = await get_or_create_workspace(session, name="DrinkX UX Sandbox")
    pipeline = await get_or_create_pipeline(session, workspace=ws)
    res = await session.execute(
        select(Stage).where(Stage.pipeline_id == pipeline.id).order_by(Stage.position)
    )
    stages = list(res.scalars().all())

    admin = await get_or_create_user(session, workspace=ws, email="ux-admin@drinkx.tech", name="Админ UX", role="admin")
    head = await get_or_create_user(session, workspace=ws, email="ux-head@drinkx.tech", name="Руководитель UX", role="head")
    owner = await get_or_create_user(session, workspace=ws, email="ux-owner@drinkx.tech", name="Менеджер Владелец", role="manager")
    other = await get_or_create_user(session, workspace=ws, email="ux-other@drinkx.tech", name="Менеджер Другой", role="manager")
    third = await get_or_create_user(session, workspace=ws, email="ux-third@drinkx.tech", name="Менеджер Третий", role="manager")

    managers = [owner, other, third]
    leads: list[Lead] = []
    for i in range(60):
        if i % 4 == 0:
            assigned_to, status = None, "pool"
        else:
            assigned_to, status = managers[i % len(managers)].id, "assigned"
        lead = await get_or_create_lead(
            session,
            workspace=ws,
            pipeline=pipeline,
            stages=stages,
            name=company_name(i),
            assigned_to=assigned_to,
            assignment_status=status,
            idx=i,
        )
        leads.append(lead)
    await session.flush()

    owner_leads = [l for l in leads if l.assigned_to == owner.id]
    other_leads = [l for l in leads if l.assigned_to == other.id]

    tasks_created = 0
    # Lead-scoped tasks, explicit assignee, mixed due/done.
    for i, lead in enumerate(leads[:24]):
        assignee = owner.id if lead in owner_leads else (other.id if lead in other_leads else None)
        await get_or_create_task(
            session,
            workspace=ws,
            lead=lead,
            assignee_user_id=assignee,
            subject=f"Связаться с {lead.company_name}",
            due_offset_days=(i % 14) - 7,  # mix of overdue/upcoming
            done=(i % 5 == 0),
        )
        tasks_created += 1

    # Lead-scoped tasks with NO explicit assignee (falls back to lead owner).
    for i, lead in enumerate(leads[24:32]):
        await get_or_create_task(
            session,
            workspace=ws,
            lead=lead,
            assignee_user_id=None,
            subject=f"Отправить КП - {lead.company_name}",
            due_offset_days=(i % 10) - 3,
            done=False,
        )
        tasks_created += 1

    # Standalone tasks (no lead), some with assignee, some without.
    standalone_subjects = [
        ("Сдать еженедельный отчёт", head.id, 1, False),
        ("Проверить пул лидов", None, 0, False),
        ("Обновить скрипт звонка", owner.id, -2, True),
        ("Синхронизация с командой", other.id, 3, False),
        ("Аудит просроченных сделок", admin.id, -1, False),
        ("Ревью карточек приоритета A", head.id, 2, False),
        ("Настроить уведомления", third.id, 5, False),
        ("Согласовать КП шаблон", None, -5, True),
    ]
    for subject, assignee, offset, done in standalone_subjects:
        await get_or_create_task(
            session,
            workspace=ws,
            lead=None,
            assignee_user_id=assignee,
            subject=subject,
            due_offset_days=offset,
            done=done,
        )
        tasks_created += 1

    return {
        "workspace": ws,
        "admin": admin,
        "head": head,
        "owner": owner,
        "other": other,
        "third": third,
        "leads": leads,
        "tasks_created": tasks_created,
    }


async def seed_workspace_2(session: AsyncSession) -> dict:
    """A second, isolated workspace - used to test cross-workspace access
    denial. NOTE: production sign-in only ever creates ONE shared workspace
    (see app/auth/services.py bootstrap comment); this second workspace is a
    seed-only construct, reachable only by users whose supabase_user_id
    matches a token minted for them directly (see UX-ENV/README.md)."""
    ws = await get_or_create_workspace(session, name="DrinkX UX Sandbox 2")
    pipeline = await get_or_create_pipeline(session, workspace=ws)
    res = await session.execute(
        select(Stage).where(Stage.pipeline_id == pipeline.id).order_by(Stage.position)
    )
    stages = list(res.scalars().all())

    admin2 = await get_or_create_user(
        session, workspace=ws, email="ux-admin2@drinkx.tech", name="Админ Второго Воркспейса", role="admin"
    )
    manager2 = await get_or_create_user(
        session, workspace=ws, email="ux-manager2@drinkx.tech", name="Менеджер Второго Воркспейса", role="manager"
    )

    leads = []
    for i in range(6):
        assigned_to, status = (manager2.id, "assigned") if i % 2 else (None, "pool")
        lead = await get_or_create_lead(
            session,
            workspace=ws,
            pipeline=pipeline,
            stages=stages,
            name=company_name(1000 + i, suffix="-WS2"),
            assigned_to=assigned_to,
            assignment_status=status,
            idx=i,
        )
        leads.append(lead)

    for i, lead in enumerate(leads[:3]):
        await get_or_create_task(
            session,
            workspace=ws,
            lead=lead,
            assignee_user_id=manager2.id,
            subject=f"[WS2] Связаться с {lead.company_name}",
            due_offset_days=i,
            done=False,
        )

    return {"workspace": ws, "admin2": admin2, "manager2": manager2, "leads": leads}


def write_sample_csv(path: str = "/tmp/ux_leads_import_sample.csv") -> str:
    lines = [
        "Название компании,Сегмент,Город,Email,Телефон,Сайт",
        "Кофе Групп Импорт,retail,Москва,import1@example.com,+79001234567,https://coffeegroup.example",
        "Стан Трейд Импорт,horeca,Казань,import2@example.com,+79002345678,https://stantrade.example",
        "Ритейл Плюс Импорт,qsr,Новосибирск,,+79003456789,",
        "Юнион Сервис Импорт,gas_station,Краснодар,import4@example.com,,https://unionservice.example",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


async def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    try:
        assert_disposable(database_url, purpose="seed_ux_synthetic")
    except Exception as exc:  # UnsafeDatabaseTarget
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        ws1 = await seed_workspace_1(session)
        ws2 = await seed_workspace_2(session)
        await session.commit()

    csv_path = write_sample_csv()

    print("Seed OK")
    print(f"  Workspace 1: {ws1['workspace'].id}  ({ws1['workspace'].name})")
    print(f"    admin={ws1['admin'].email}  head={ws1['head'].email}")
    print(f"    owner={ws1['owner'].email}  other={ws1['other'].email}  third={ws1['third'].email}")
    print(f"    leads={len(ws1['leads'])}  tasks_created_this_pass={ws1['tasks_created']}")
    print(f"  Workspace 2: {ws2['workspace'].id}  ({ws2['workspace'].name})")
    print(f"    admin2={ws2['admin2'].email}  manager2={ws2['manager2'].email}  leads={len(ws2['leads'])}")
    print(f"  Sample import CSV: {csv_path}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
