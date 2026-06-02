# Website Leads Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заявки с 3–4 сайтов DrinkX приходят в CRM как входящие лиды с меткой источника, назначаются фиксированному менеджеру сайта, сразу превращаются в задачу «Связаться», а CRM шлёт письмо отделу; приём защищён ключом `X-Form-Key`.

**Architecture:** Расширяем существующий домен `forms` (Sprint 2.2). Добавляем 5 колонок в `web_forms` (миграция 0041), ветку маршрутизации+задачи в `lead_factory`, проверку ключа в `submit_form`, email-уведомление через готовый `send_email`, агрегат аналитики и админ-поля. Без новых таблиц.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, pytest (mock-only — sqlalchemy застаблен в тестах), Next.js 15 + TanStack Query (frontend).

**Spec:** `docs/superpowers/specs/2026-06-02-website-leads-intake-design.md`

---

## File Structure

| Файл | Что делает |
|---|---|
| `apps/api/alembic/versions/20260602_0041_webform_routing_intake.py` | миграция: +5 колонок в `web_forms` |
| `apps/api/app/forms/models.py` | +5 ORM-колонок |
| `apps/api/app/forms/schemas.py` | новые поля в Create/Update/Out + `FormChannelStat`/`FormAnalyticsOut` |
| `apps/api/app/forms/lead_factory.py` | назначение владельца + авто-задача «Связаться» |
| `apps/api/app/forms/public_routers.py` | проверка `X-Form-Key`, email отделу, уведомление владельцу |
| `apps/api/app/forms/services.py` | валидация `default_assignee_id`, генерация/ротация `ingest_token`, аналитика |
| `apps/api/app/forms/repositories.py` | запрос-агрегат аналитики |
| `apps/api/app/forms/routers.py` | новые поля в serialize, `POST /{id}/rotate-key`, `GET /analytics` |
| `apps/api/tests/test_webforms.py` | расширяем mock-тесты |
| `apps/web/lib/hooks/use-forms.ts` | типы + хук аналитики |
| `apps/web/components/forms/FormEditor.tsx` | поля: владелец, SLA, канал, notify_email, S2S, ключ |
| `apps/web/app/(app)/forms/page.tsx` | таблица аналитики по каналам |
| `docs/integrations/website-forms-api.md` | контракт для разработчиков сайтов |

---

## Task 1: DB migration + ORM columns

**Files:**
- Create: `apps/api/alembic/versions/20260602_0041_webform_routing_intake.py`
- Modify: `apps/api/app/forms/models.py`

- [ ] **Step 1: Write the migration**

Create `apps/api/alembic/versions/20260602_0041_webform_routing_intake.py`:

```python
"""WebForm routing + intake: assignee, sla, source_label, notify_email, ingest_token.

Revision ID: 0041_webform_routing_intake
Revises: 0040_normalize_company_segments
Create Date: 2026-06-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0041_webform_routing_intake"
down_revision = "0040_normalize_company_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "web_forms",
        sa.Column("default_assignee_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_web_forms_default_assignee",
        "web_forms", "users",
        ["default_assignee_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "web_forms",
        sa.Column("contact_task_sla_hours", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column("web_forms", sa.Column("source_label", sa.String(length=120), nullable=True))
    op.add_column("web_forms", sa.Column("notify_email", sa.String(length=254), nullable=True))
    op.add_column("web_forms", sa.Column("ingest_token", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_constraint("fk_web_forms_default_assignee", "web_forms", type_="foreignkey")
    op.drop_column("web_forms", "ingest_token")
    op.drop_column("web_forms", "notify_email")
    op.drop_column("web_forms", "source_label")
    op.drop_column("web_forms", "contact_task_sla_hours")
    op.drop_column("web_forms", "default_assignee_id")
```

- [ ] **Step 2: Add ORM columns**

In `apps/api/app/forms/models.py`, inside `class WebForm`, after the `submissions_count` column (line ~69), add:

```python
    # Sprint «Website Leads Intake» — routing + intake hardening (migration 0041).
    default_assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_task_sla_hours: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2", nullable=False
    )
    source_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notify_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    # S2S secret. NULL → open form (browser/embed). NOT NULL → submit
    # requires matching X-Form-Key header.
    ingest_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 3: Verify migration imports and py_compile**

Run: `cd apps/api && python -m py_compile alembic/versions/20260602_0041_webform_routing_intake.py app/forms/models.py`
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/api/alembic/versions/20260602_0041_webform_routing_intake.py apps/api/app/forms/models.py
git commit -m "feat(forms): migration 0041 — webform routing + intake columns"
```

---

## Task 2: lead_factory — route to owner + create contact task

**Files:**
- Modify: `apps/api/app/forms/lead_factory.py`
- Test: `apps/api/tests/test_webforms.py`

- [ ] **Step 1: Write failing tests**

Append to `apps/api/tests/test_webforms.py` (the `_make_lead_factory_env`, `_make_form`, `_make_session` helpers already exist near the top):

```python
@pytest.mark.asyncio
async def test_routing_assigns_owner_and_creates_task():
    """Form with default_assignee_id → lead becomes assigned to that user
    and a type='task' Activity with a due date is created."""
    from app.forms import lead_factory as lf_mod

    owner = uuid.uuid4()
    leads, activities, patches = _make_lead_factory_env()
    form = _make_form(default_assignee_id=owner, contact_task_sla_hours=2)
    session = _make_session()

    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        # safe_evaluate_trigger is imported lazily inside the factory — stub it.
        stack.enter_context(patch(
            "app.automation_builder.services.safe_evaluate_trigger",
            new=AsyncMock(),
        ))
        lead = await lf_mod.create_lead_from_submission(
            session, form=form, payload={"company": "ACME"},
            source_domain="acme.ru", utm=None,
        )

    assert lead.assignment_status == "assigned"
    assert lead.assigned_to == owner
    assert lead.assigned_at is not None
    tasks = [a for a in activities if a.get("type") == "task"]
    assert len(tasks) == 1
    assert tasks[0]["task_due_at"] is not None
    assert tasks[0]["lead_id"] == lead.id


@pytest.mark.asyncio
async def test_no_owner_leaves_lead_in_pool_no_task():
    """Form without default_assignee_id → lead stays in pool, no task."""
    from app.forms import lead_factory as lf_mod

    leads, activities, patches = _make_lead_factory_env()
    form = _make_form(default_assignee_id=None, contact_task_sla_hours=2)
    session = _make_session()

    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(patch(
            "app.automation_builder.services.safe_evaluate_trigger",
            new=AsyncMock(),
        ))
        lead = await lf_mod.create_lead_from_submission(
            session, form=form, payload={"company": "ACME"},
            source_domain="acme.ru", utm=None,
        )

    assert lead.assignment_status == "pool"
    assert getattr(lead, "assigned_to", None) is None
    assert [a for a in activities if a.get("type") == "task"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_webforms.py::test_routing_assigns_owner_and_creates_task tests/test_webforms.py::test_no_owner_leaves_lead_in_pool_no_task -v`
Expected: FAIL — lead stays `pool`, no task Activity captured.

- [ ] **Step 3: Implement routing + task in lead_factory**

In `apps/api/app/forms/lead_factory.py`, update the imports at top (add `datetime`):

```python
from datetime import datetime, timedelta, timezone
```

Then, after the `await session.flush()` that persists the lead (line ~161, before the `if notes:` block), insert:

```python
    # Sprint «Website Leads Intake»: route to the form's fixed owner and
    # drop a "Связаться" task. No owner → lead stays in pool (legacy
    # behaviour). Deterministic, NOT AI — this is system-created routing.
    if form.default_assignee_id:
        now = datetime.now(timezone.utc)
        lead.assignment_status = "assigned"
        lead.assigned_to = form.default_assignee_id
        lead.assigned_at = now
        sla_hours = form.contact_task_sla_hours or 2
        session.add(
            Activity(
                lead_id=lead.id,
                user_id=None,
                type="task",
                body="Связаться с заявкой",
                task_due_at=now + timedelta(hours=sla_hours),
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && python -m pytest tests/test_webforms.py -v`
Expected: PASS (all webforms tests green).

- [ ] **Step 5: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/api/app/forms/lead_factory.py apps/api/tests/test_webforms.py
git commit -m "feat(forms): route website leads to fixed owner + create contact task"
```

---

## Task 3: submit_form — enforce X-Form-Key when ingest_token is set

**Files:**
- Modify: `apps/api/app/forms/public_routers.py`
- Test: `apps/api/tests/test_webforms.py`

- [ ] **Step 1: Write the failing test (pure helper, no FastAPI wiring)**

Add a small pure helper to keep the check unit-testable. Append test to `apps/api/tests/test_webforms.py`:

```python
def test_ingest_key_check():
    from app.forms.public_routers import _ingest_key_ok

    # Open form (no token) — always ok regardless of header.
    assert _ingest_key_ok(form_token=None, provided=None) is True
    assert _ingest_key_ok(form_token=None, provided="anything") is True
    # Protected form — exact match required.
    assert _ingest_key_ok(form_token="secret", provided="secret") is True
    assert _ingest_key_ok(form_token="secret", provided="wrong") is False
    assert _ingest_key_ok(form_token="secret", provided=None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_webforms.py::test_ingest_key_check -v`
Expected: FAIL with `ImportError`/`AttributeError` — `_ingest_key_ok` not defined.

- [ ] **Step 3: Implement the helper + wire into submit_form**

In `apps/api/app/forms/public_routers.py`, add `import hmac` near the top imports, then add this helper after `_extract_utm` (~line 92):

```python
def _ingest_key_ok(*, form_token: str | None, provided: str | None) -> bool:
    """Open form (no token) accepts any caller. Protected form requires
    a constant-time exact match on X-Form-Key."""
    if not form_token:
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided, form_token)
```

In `submit_form`, after the `if not form.is_active:` block (~line 172) and before `src_domain = ...`, insert:

```python
    if not _ingest_key_ok(
        form_token=form.ingest_token,
        provided=request.headers.get("x-form-key"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или отсутствующий ключ формы",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_webforms.py::test_ingest_key_check -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/api/app/forms/public_routers.py apps/api/tests/test_webforms.py
git commit -m "feat(forms): enforce X-Form-Key on protected webforms"
```

---

## Task 4: Email to team + in-app notify owner on submit

**Files:**
- Modify: `apps/api/app/forms/public_routers.py`
- Test: `apps/api/tests/test_webforms.py`

- [ ] **Step 1: Write the failing test**

The recipient-collection logic is the testable unit. Append test:

```python
def test_collect_email_recipients_dedupes():
    from app.forms.public_routers import _collect_email_recipients

    # Owner email + notify_email, deduped, empties dropped.
    assert _collect_email_recipients(
        owner_email="m@x.ru", notify_email="sales@x.ru"
    ) == ["m@x.ru", "sales@x.ru"]
    assert _collect_email_recipients(
        owner_email="m@x.ru", notify_email="m@x.ru"
    ) == ["m@x.ru"]
    assert _collect_email_recipients(owner_email=None, notify_email=None) == []
    assert _collect_email_recipients(owner_email="", notify_email="sales@x.ru") == ["sales@x.ru"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_webforms.py::test_collect_email_recipients_dedupes -v`
Expected: FAIL — `_collect_email_recipients` not defined.

- [ ] **Step 3: Implement recipients helper + email sender + wire-in**

In `apps/api/app/forms/public_routers.py`, add the helper after `_ingest_key_ok`:

```python
def _collect_email_recipients(
    *, owner_email: str | None, notify_email: str | None
) -> list[str]:
    """Dedup-preserving-order list of internal notification recipients."""
    out: list[str] = []
    for addr in (owner_email, notify_email):
        a = (addr or "").strip()
        if a and a not in out:
            out.append(a)
    return out
```

Add the email sender (best-effort, never raises) after `_notify_workspace_admins`:

```python
async def _send_lead_email_notification(
    session: AsyncSession,
    *,
    lead,
    form,
) -> None:
    """CRM-sent internal email: owner + form.notify_email. Best-effort —
    a relay hiccup must never 5xx the public submit."""
    from sqlalchemy import select

    from app.auth.models import User
    from app.notifications.email_sender import send_email

    try:
        owner_email: str | None = None
        if lead.assigned_to:
            res = await session.execute(
                select(User.email).where(User.id == lead.assigned_to)
            )
            owner_email = res.scalar_one_or_none()

        recipients = _collect_email_recipients(
            owner_email=owner_email, notify_email=form.notify_email
        )
        if not recipients:
            return

        settings = get_settings()
        web_base = settings.web_base_url.rstrip("/") if getattr(settings, "web_base_url", "") else ""
        channel = form.source_label or form.name
        link = f"{web_base}/leads/{lead.id}" if web_base else str(lead.id)
        html = (
            f"<p>Новая заявка с сайта: <b>{channel}</b></p>"
            f"<p>Компания: {lead.company_name}</p>"
            f'<p><a href="{link}">Открыть карточку лида</a></p>'
        )
        for to in recipients:
            await send_email(
                to=to,
                subject=f"Новая заявка с сайта: {lead.company_name}",
                html=html,
            )
    except Exception as exc:  # noqa: BLE001 — public flow must not 5xx
        log.warning("forms.email_notify_failed", error=str(exc)[:200])
```

In `submit_form`, after the `await _notify_workspace_admins(...)` call (~line 234), add:

```python
    await _send_lead_email_notification(db, lead=lead, form=form)
```

> If `settings.web_base_url` does not exist, add it to `app/config.py` Settings with a sensible default `web_base_url: str = "https://crm.drinkx.tech"`. Check first with `grep -n "web_base_url\|api_base_url" app/config.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_webforms.py::test_collect_email_recipients_dedupes -v`
Expected: PASS.

- [ ] **Step 5: Add in-app notify for the owner**

In `_notify_workspace_admins` (or a sibling call), after the admin loop, also notify the owner. Simplest: in `submit_form`, the existing `_notify_workspace_admins` stays; add owner notify inside `_send_lead_email_notification`? No — keep concerns separate. Instead, inside `_notify_workspace_admins`, after the admin loop, add:

```python
        # Owner of a routed lead also gets an in-app notification.
        if lead_id is not None:
            from app.leads.models import Lead as _Lead
            res2 = await session.execute(select(_Lead.assigned_to).where(_Lead.id == lead_id))
            owner_id = res2.scalar_one_or_none()
            if owner_id:
                await safe_notify(
                    session, workspace_id=workspace_id, user_id=owner_id,
                    kind="system", title="Новая заявка с сайта",
                    body=f'"{form_name}" — {company_name}', lead_id=lead_id,
                )
```

- [ ] **Step 6: Run full forms test suite**

Run: `cd apps/api && python -m pytest tests/test_webforms.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/api/app/forms/public_routers.py apps/api/app/config.py apps/api/tests/test_webforms.py
git commit -m "feat(forms): CRM emails team + in-app notifies owner on new website lead"
```

---

## Task 5: Admin API — new fields, assignee validation, token toggle + rotate

**Files:**
- Modify: `apps/api/app/forms/schemas.py`, `apps/api/app/forms/services.py`, `apps/api/app/forms/routers.py`
- Test: `apps/api/tests/test_webforms.py`

- [ ] **Step 1: Extend schemas**

In `apps/api/app/forms/schemas.py`:

`WebFormCreateIn` — add fields:

```python
    default_assignee_id: UUID | None = None
    contact_task_sla_hours: int = Field(default=2, ge=1, le=240)
    source_label: str | None = Field(default=None, max_length=120)
    notify_email: str | None = Field(default=None, max_length=254)
    require_key: bool = False  # True → server generates ingest_token
```

`WebFormUpdateIn` — add:

```python
    default_assignee_id: UUID | None = None
    contact_task_sla_hours: int | None = Field(default=None, ge=1, le=240)
    source_label: str | None = Field(default=None, max_length=120)
    notify_email: str | None = Field(default=None, max_length=254)
    require_key: bool | None = None
```

`WebFormOut` — add (so admin sees them):

```python
    default_assignee_id: UUID | None = None
    contact_task_sla_hours: int = 2
    source_label: str | None = None
    notify_email: str | None = None
    ingest_token: str | None = None
```

Add analytics schemas at the end of the file:

```python
class FormChannelStat(BaseModel):
    form_id: UUID
    channel: str          # source_label or name
    submissions: int
    leads: int
    won: int
    conversion: float     # won / leads, 0.0 when leads == 0


class FormAnalyticsOut(BaseModel):
    rows: list[FormChannelStat]
    total_submissions: int
    total_leads: int
    total_won: int
```

- [ ] **Step 2: Write failing test for assignee validation**

Append to `apps/api/tests/test_webforms.py`:

```python
@pytest.mark.asyncio
async def test_create_form_rejects_foreign_assignee():
    """default_assignee_id must belong to the caller's workspace."""
    db = AsyncMock()

    async def fake_user_in_ws(session, *, user_id, workspace_id):
        return False  # assignee not in workspace

    with patch("app.forms.services._assignee_in_workspace", new=fake_user_in_ws):
        with pytest.raises(svc_mod.WebFormInvalidTarget):
            await svc_mod.create_form(
                db, workspace_id=WS, user_id=uuid.uuid4(),
                name="F", fields_json=[],
                default_assignee_id=uuid.uuid4(),
            )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_webforms.py::test_create_form_rejects_foreign_assignee -v`
Expected: FAIL — `create_form` does not accept `default_assignee_id`.

- [ ] **Step 4: Implement service changes**

In `apps/api/app/forms/services.py`, add `import secrets` at top, and a validator:

```python
async def _assignee_in_workspace(
    session: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> bool:
    from sqlalchemy import select

    from app.auth.models import User

    res = await session.execute(
        select(User.id).where(User.id == user_id, User.workspace_id == workspace_id).limit(1)
    )
    return res.scalar_one_or_none() is not None
```

Extend `create_form` signature with the new kwargs and validate + pass through:

```python
async def create_form(
    session, *, workspace_id, user_id, name, fields_json,
    target_pipeline_id=None, target_stage_id=None, redirect_url=None,
    default_assignee_id=None, contact_task_sla_hours=2,
    source_label=None, notify_email=None, require_key=False,
):
    await _validate_target(session, workspace_id=workspace_id,
        target_pipeline_id=target_pipeline_id, target_stage_id=target_stage_id)
    if default_assignee_id is not None:
        if not await _assignee_in_workspace(session, user_id=default_assignee_id, workspace_id=workspace_id):
            raise WebFormInvalidTarget("default_assignee_id does not belong to this workspace")
    ingest_token = secrets.token_urlsafe(32) if require_key else None
    # ... inside the retry loop, pass these to repo.create():
    #     default_assignee_id=default_assignee_id,
    #     contact_task_sla_hours=contact_task_sla_hours,
    #     source_label=source_label, notify_email=notify_email,
    #     ingest_token=ingest_token,
```

In `update_form`, after building `cleaned`, validate assignee if present and handle `require_key`:

```python
    if cleaned.get("default_assignee_id") is not None:
        if not await _assignee_in_workspace(
            session, user_id=cleaned["default_assignee_id"], workspace_id=workspace_id
        ):
            raise WebFormInvalidTarget("default_assignee_id does not belong to this workspace")
    if "require_key" in cleaned:
        rk = cleaned.pop("require_key")
        cleaned["ingest_token"] = secrets.token_urlsafe(32) if rk else None
```

Add a rotate-key service:

```python
async def rotate_key(session, *, form_id, workspace_id):
    form = await get_form_or_404(session, form_id=form_id, workspace_id=workspace_id)
    form.ingest_token = secrets.token_urlsafe(32)
    await session.flush()
    return form
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_webforms.py::test_create_form_rejects_foreign_assignee -v`
Expected: PASS.

- [ ] **Step 6: Wire router**

In `apps/api/app/forms/routers.py`:

`create_form` handler — pass the new fields:

```python
        form = await svc.create_form(
            db, workspace_id=user.workspace_id, user_id=user.id,
            name=payload.name, fields_json=payload.fields_json,
            target_pipeline_id=payload.target_pipeline_id,
            target_stage_id=payload.target_stage_id,
            redirect_url=payload.redirect_url,
            default_assignee_id=payload.default_assignee_id,
            contact_task_sla_hours=payload.contact_task_sla_hours,
            source_label=payload.source_label,
            notify_email=payload.notify_email,
            require_key=payload.require_key,
        )
```

(`update_form` already forwards `patch = payload.model_dump(exclude_unset=True)` — the new keys flow through automatically.)

Add the rotate endpoint after `delete_form`:

```python
@router.post("/{form_id}/rotate-key", response_model=WebFormOut)
async def rotate_form_key(
    form_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> WebFormOut:
    try:
        form = await svc.rotate_key(db, form_id=form_id, workspace_id=user.workspace_id)
    except svc.WebFormNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    await db.commit()
    await db.refresh(form)
    return serialize_form(form)
```

> `serialize_form` calls `WebFormOut.model_validate(form)` → the new ORM columns (including `ingest_token`) flow into the response via `from_attributes=True`. No change needed there.

- [ ] **Step 7: Run full forms suite + py_compile**

Run: `cd apps/api && python -m pytest tests/test_webforms.py -v && python -m py_compile app/forms/schemas.py app/forms/services.py app/forms/routers.py`
Expected: PASS, no compile errors.

- [ ] **Step 8: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/api/app/forms/schemas.py apps/api/app/forms/services.py apps/api/app/forms/routers.py apps/api/tests/test_webforms.py
git commit -m "feat(forms): admin fields for routing/SLA/channel/notify + ingest key toggle & rotate"
```

---

## Task 6: Channel analytics endpoint

**Files:**
- Modify: `apps/api/app/forms/repositories.py`, `apps/api/app/forms/services.py`, `apps/api/app/forms/routers.py`
- Test: `apps/api/tests/test_form_stats.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_form_stats.py` (uses the same sqlalchemy-stub pattern as test_webforms — copy the `_stub_sqlalchemy()` block if that file doesn't already have it; check the file header first):

```python
@pytest.mark.asyncio
async def test_channel_analytics_shapes_rows_and_totals():
    from app.forms import services as svc

    # Stub the repo aggregate: two forms with counts.
    f1, f2 = uuid.uuid4(), uuid.uuid4()
    async def fake_agg(db, *, workspace_id, date_from, date_to):
        return [
            {"form_id": f1, "channel": "Главный сайт", "submissions": 10, "leads": 8, "won": 2},
            {"form_id": f2, "channel": "Лендинг QSR", "submissions": 5, "leads": 5, "won": 0},
        ]

    with patch("app.forms.repositories.channel_analytics", new=fake_agg):
        out = await svc.get_channel_analytics(
            AsyncMock(), workspace_id=WS, date_from=None, date_to=None
        )

    assert out.total_submissions == 15
    assert out.total_leads == 13
    assert out.total_won == 2
    assert out.rows[0].conversion == 0.25
    assert out.rows[1].conversion == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_form_stats.py::test_channel_analytics_shapes_rows_and_totals -v`
Expected: FAIL — `get_channel_analytics` not defined.

- [ ] **Step 3: Implement repository aggregate**

In `apps/api/app/forms/repositories.py`, add:

```python
async def channel_analytics(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    date_from=None,
    date_to=None,
) -> list[dict]:
    """One row per form in the workspace: submissions, distinct leads,
    won leads. Date filters apply to FormSubmission.created_at."""
    from sqlalchemy import case, func

    from app.leads.models import Lead

    won = func.count(func.distinct(case((Lead.won_at.isnot(None), Lead.id))))
    q = (
        select(
            WebForm.id.label("form_id"),
            func.coalesce(WebForm.source_label, WebForm.name).label("channel"),
            func.count(func.distinct(FormSubmission.id)).label("submissions"),
            func.count(func.distinct(FormSubmission.lead_id)).label("leads"),
            won.label("won"),
        )
        .select_from(WebForm)
        .outerjoin(FormSubmission, FormSubmission.web_form_id == WebForm.id)
        .outerjoin(Lead, Lead.id == FormSubmission.lead_id)
        .where(WebForm.workspace_id == workspace_id)
        .group_by(WebForm.id, func.coalesce(WebForm.source_label, WebForm.name))
    )
    if date_from is not None:
        q = q.where(FormSubmission.created_at >= date_from)
    if date_to is not None:
        q = q.where(FormSubmission.created_at <= date_to)
    rows = await session.execute(q)
    return [dict(r._mapping) for r in rows]
```

- [ ] **Step 4: Implement service**

In `apps/api/app/forms/services.py`, add:

```python
async def get_channel_analytics(db, *, workspace_id, date_from=None, date_to=None):
    from app.forms.schemas import FormAnalyticsOut, FormChannelStat

    raw = await repo.channel_analytics(
        db, workspace_id=workspace_id, date_from=date_from, date_to=date_to
    )
    rows = []
    for r in raw:
        leads = int(r["leads"] or 0)
        won = int(r["won"] or 0)
        rows.append(FormChannelStat(
            form_id=r["form_id"], channel=r["channel"],
            submissions=int(r["submissions"] or 0), leads=leads, won=won,
            conversion=round(won / leads, 4) if leads else 0.0,
        ))
    return FormAnalyticsOut(
        rows=rows,
        total_submissions=sum(x.submissions for x in rows),
        total_leads=sum(x.leads for x in rows),
        total_won=sum(x.won for x in rows),
    )
```

- [ ] **Step 5: Add router endpoint**

In `apps/api/app/forms/routers.py`, add (import `FormAnalyticsOut` and `datetime` as needed). Mount BEFORE `/{form_id}` so `analytics` isn't captured as a UUID path param:

```python
@router.get("/analytics", response_model=FormAnalyticsOut)
async def get_analytics(
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> FormAnalyticsOut:
    return await svc.get_channel_analytics(
        db, workspace_id=user.workspace_id, date_from=date_from, date_to=date_to
    )
```

> **Ordering note:** FastAPI matches routes in declaration order. `GET /analytics` MUST be declared above `GET /{form_id}` (line ~83) or `"analytics"` will be parsed as a `form_id: UUID` and 422. Move the new function above `get_form`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps/api && python -m pytest tests/test_form_stats.py -v && python -m py_compile app/forms/repositories.py app/forms/services.py app/forms/routers.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/api/app/forms/repositories.py apps/api/app/forms/services.py apps/api/app/forms/routers.py apps/api/tests/test_form_stats.py
git commit -m "feat(forms): channel analytics endpoint (submissions/leads/won per source)"
```

---

## Task 7: Frontend — FormEditor fields + integration block

**Files:**
- Modify: `apps/web/lib/hooks/use-forms.ts`, `apps/web/components/forms/FormEditor.tsx`

- [ ] **Step 1: Extend the WebForm type + create/update payloads**

In `apps/web/lib/hooks/use-forms.ts`, add to the `WebForm` type and the create/update input types (match existing naming):

```ts
  default_assignee_id?: string | null;
  contact_task_sla_hours?: number;
  source_label?: string | null;
  notify_email?: string | null;
  require_key?: boolean;
  ingest_token?: string | null;
```

Add a rotate-key mutation hook mirroring the existing update hook, calling `POST /api/forms/${id}/rotate-key`.

- [ ] **Step 2: Add the form fields in FormEditor**

In `apps/web/components/forms/FormEditor.tsx`, add controlled inputs (follow the file's existing field/styling pattern — spacing scale 4-8-12-16-24-32):

- «Ответственный менеджер» — `<select>` populated from the workspace users list (reuse the existing team/users hook; check `apps/web/lib/hooks` for `use-team`/`use-users`). Value → `default_assignee_id`. Include an empty option «— в общий пул —».
- «SLA, часов» — `<input type="number" min={1} max={240}>` → `contact_task_sla_hours`, default 2.
- «Название канала (для аналитики)» — text → `source_label`.
- «Email для уведомлений» — `<input type="email">` → `notify_email`.
- «Защищённый приём (S2S ключ)» — checkbox → `require_key`.

- [ ] **Step 3: Add the integration block**

When the form has `ingest_token`, render a read-only block showing:
- the `<script>` embed snippet (already returned as `embed_snippet`),
- the S2S `curl` example:

```ts
const curlExample = `curl -X POST ${apiBase}/api/public/forms/${form.slug}/submit \\
  -H "Content-Type: application/json" \\
  -H "X-Form-Key: ${form.ingest_token}" \\
  -d '{"company":"ООО Ромашка","phone":"+7...","comment":"..."}'`;
```

- a «Перевыпустить ключ» button calling the rotate-key mutation.

- [ ] **Step 4: Typecheck + build**

Run: `cd apps/web && npm run typecheck && npm run lint && pnpm build`
Expected: clean (per CLAUDE.md the `pnpm build` gate is mandatory for routing-touching changes; run it regardless here).

- [ ] **Step 5: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/web/lib/hooks/use-forms.ts apps/web/components/forms/FormEditor.tsx
git commit -m "feat(web): FormEditor — owner/SLA/channel/notify fields + S2S key block"
```

---

## Task 8: Frontend — channel analytics table on /forms

**Files:**
- Modify: `apps/web/lib/hooks/use-forms.ts`, `apps/web/app/(app)/forms/page.tsx`

- [ ] **Step 1: Add the analytics query hook**

In `apps/web/lib/hooks/use-forms.ts`, add:

```ts
export type FormChannelStat = {
  form_id: string; channel: string; submissions: number;
  leads: number; won: number; conversion: number;
};
export type FormAnalytics = {
  rows: FormChannelStat[]; total_submissions: number;
  total_leads: number; total_won: number;
};

export function useFormAnalytics() {
  return useQuery({
    queryKey: ["forms", "analytics"],
    queryFn: () => apiClient.get<FormAnalytics>("/api/forms/analytics"),
  });
}
```

(Match the actual `apiClient` import + query patterns already in the file.)

- [ ] **Step 2: Render the table**

In `apps/web/app/(app)/forms/page.tsx`, add a section «Аналитика по каналам» above or below the forms list: a table with columns Канал / Заявки / Лиды / Выиграно / Конверсия, plus a totals row. Use `useFormAnalytics()`. Format `conversion` as `${(c*100).toFixed(0)}%`.

- [ ] **Step 3: Typecheck + build**

Run: `cd apps/web && npm run typecheck && npm run lint && pnpm build`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add apps/web/lib/hooks/use-forms.ts "apps/web/app/(app)/forms/page.tsx"
git commit -m "feat(web): channel analytics table on /forms"
```

---

## Task 9: Integration contract docs for site developers

**Files:**
- Create: `docs/integrations/website-forms-api.md`

- [ ] **Step 1: Write the doc**

Create `docs/integrations/website-forms-api.md` covering:

- **Endpoint:** `POST https://crm.drinkx.tech/api/public/forms/{slug}/submit`
- **Headers:** `Content-Type: application/json`; `X-Form-Key: <ключ>` (для защищённых форм — взять в CRM на странице формы).
- **Тело (JSON):** канонические ключи и их синонимы (`company_name`/`название`/`company`, `email`/`почта`, `phone`/`телефон`/`тел`, `website`/`сайт`, `city`/`город`, `inn`/`инн`, `comment`/`сообщение`/`вопрос`), плюс любые `utm_*`. Неизвестные ключи сохраняются в `raw_payload`.
- **Ответы:** `200 {"ok": true, "redirect": null|url}`; `401` неверный/нет ключа; `404` форма не найдена; `410` форма выключена; `429` rate-limit (повторить через минуту).
- **Пример curl** (как в Task 7 Step 3).
- **Пример Node.js** — бэкенд сайта: после отправки письма себе делает `fetch` в CRM с ключом; CRM-вызов в `try/catch`, чтобы падение CRM не ломало отправку формы на сайте.
- **Замечание:** для форм с ключом отправлять с сервера сайта (ключ — секрет, не светить в браузере). Открытые формы (без ключа) можно слать из браузера или встроить `embed.js`.

- [ ] **Step 2: Commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add docs/integrations/website-forms-api.md
git commit -m "docs(integrations): website→CRM forms API contract"
```

---

## Task 10: Full backend test pass + sprint checkbox + push

- [ ] **Step 1: Run the whole backend suite**

Run: `cd apps/api && python -m pytest -q`
Expected: all green (or pre-existing failures unrelated to forms — note them, don't fix unrelated).

- [ ] **Step 2: Add a sprint note**

Append a `- [x]` line under the current sprint in `docs/brain/04_NEXT_SPRINT.md` summarizing «Website Leads Intake» (routing + auto-task + X-Form-Key + CRM email + channel analytics).

- [ ] **Step 3: Commit + push**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm
git add docs/brain/04_NEXT_SPRINT.md
git commit -m "docs(brain): tick Website Leads Intake"
git push
```

> **[BLOCKED — human]** Для реальной отправки писем в проде заполнить `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_FROM` в `/opt/drinkx-crm/.env`. До этого `send_email` работает в stub-режиме (письмо логируется как `[EMAIL STUB]`), функционально всё работает.

---

## Self-Review notes

- **Spec coverage:** 4.1 (Task 1), 4.2 ingest key (Task 3), 4.3 routing+task (Task 2), 4.4 in-app owner notify (Task 4 Step 5), 4.5 email (Task 4), 4.6 admin API (Task 5), 4.7 analytics (Task 6), 4.8 frontend (Tasks 7–8), 4.9 docs (Task 9). Tests §6 items 1–7 mapped across Tasks 2–6. Готовности §7 covered by Tasks 1–10.
- **Verify-before-code reminders:** `web_base_url` in config (Task 4 Step 3), users/team hook name on frontend (Task 7 Step 2), `apiClient` query pattern (Task 8), whether `test_form_stats.py` already has the sqlalchemy stub (Task 6 Step 1).
- **Route ordering:** `/analytics` before `/{form_id}` (Task 6 Step 5).
