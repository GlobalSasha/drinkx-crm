# Sprint 3.7 — Email Workflow Simplification · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/inbox` manual-triage UI and the AI-suggestion-then-confirm pattern with a multi-gate prefilter + auto-create-with-review path so email integration enriches leads without burning manager attention or AI tokens.

**Architecture:** Three execution layers. Layer 1 (auto-attach by domain/contact match) already works without LLM and gets a workspace-level off-switch for the optional AI-comment job. Layer 2 (multi-gate filter for unmatched) gains a service-local-parts Gate 3 and a tightened AI Gate 4 that auto-acts at `confidence ≥ 0.85` instead of writing a manual-triage row. Layer 3 (safety net) is a new `needs_review` boolean on `Lead` surfaced as a pill in `/leads-pool` with one-click confirm/reject.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy async, Pydantic, pytest with mock-stubbed sqlalchemy (per `apps/api/tests/test_webforms.py` pattern). Frontend: Next.js 15 App Router, React, TypeScript strict, Tailwind, TanStack Query, shadcn/ui. Celery beat/worker for the async LLM step.

**Spec:** `docs/SPRINT_3_7_EMAIL_WORKFLOW_SIMPLIFICATION.md`

**Branch:** `sprint/3.7-email-workflow` (branch from `main` after Sprint 3.7 spec PR merges).

---

## File map

**Backend (`apps/api/`):**
- Modify `app/inbox/processor.py` — add `_SERVICE_LOCAL_PARTS` constant + branch in `route_email`; replace the `InboxItem` creation + `generate_inbox_suggestion` dispatch at lines 522-551 with a direct enqueue of the new `auto_create_lead_from_email` task that carries the email payload.
- Modify `app/inbox/message_services.py` — gate the `_enqueue_lead_agent_refresh` call (around line 221) behind the new workspace setting.
- Modify `app/scheduled/jobs.py` — replace `generate_inbox_suggestion(inbox_item_id)` with `auto_create_lead_from_email(workspace_id, channel_user_id, from_email, subject, body_preview, gmail_message_id, received_at_iso)` and its async core `_run_auto_create_or_ignore`.
- Modify `app/settings/services.py` + `app/settings/schemas.py` — add `auto_lead_agent_refresh_on_inbound: bool` to `AISettingsOut`/`AISettingsUpdateIn` and resolve it via `_read_ai_section`.
- Modify `app/leads/models.py` — add `needs_review: bool` column.
- Modify `app/leads/schemas.py` — add `needs_review: bool` to `LeadOut` + `LeadListItemOut`.
- Modify `app/leads/repositories.py` — add `needs_review: bool | None = None` filter to `list_pool`.
- Modify `app/leads/routers.py` — accept `needs_review` query param on `/leads/pool`; accept `needs_review` in the existing lead PATCH body.
- Create migration `apps/api/alembic/versions/20260519_0031_lead_needs_review.py`.

**Backend tests (`apps/api/tests/`):**
- Modify `tests/test_inbox_route_email.py` — add Gate 3 cases (service local-parts).
- Create `tests/test_auto_create_lead_from_email.py` — mock-only coverage of the new Celery async core.
- Modify `tests/test_leads_source_enrichment.py` — extend the existing pool-filter test with a `needs_review` filter assertion.
- Modify `tests/test_settings_ai.py` (if exists; otherwise add new file) — assert the new setting round-trips.

**Frontend (`apps/web/`):**
- Delete `apps/web/app/(app)/inbox/page.tsx` (the whole route directory).
- Modify `apps/web/components/layout/SidebarNavContainer.tsx` — remove the «Входящие» nav item and its `useInboxCount` consumer; relocate the `UnmatchedMessagesSection` consumer.
- Move `apps/web/components/inbox/UnmatchedMessagesSection.tsx` content into `/today` (or a dedicated `/triage` route — pick one when reading `useInboxUnmatchedMessages` consumers).
- Modify `apps/web/lib/types.ts` — add `needs_review: boolean` to `LeadOut`; add `auto_lead_agent_refresh_on_inbound: boolean` to the AI settings type.
- Modify `apps/web/lib/hooks/use-leads.ts` — accept `needs_review?: boolean` filter on `usePoolLeads`.
- Modify `apps/web/components/settings/AISection.tsx` (or its file equivalent — search by `daily_budget_usd` consumer) — add the toggle row.
- Create `apps/web/components/leads-pool/NeedsReviewRow.tsx` — the pill + confirm/reject buttons.
- Modify `apps/web/app/(app)/leads-pool/page.tsx` — render `NeedsReviewRow` when `lead.needs_review` is true; add «Только AI-созданные» filter chip.

**Docs:**
- Create `docs/email-workflow.md` — manager-facing explainer.

---

## Task 1 — Backend: Lead.needs_review column + LeadOut schema

**Files:**
- Create: `apps/api/alembic/versions/20260519_0031_lead_needs_review.py`
- Modify: `apps/api/app/leads/models.py` (after `assignment_status` around line 103)
- Modify: `apps/api/app/leads/schemas.py` (`LeadOut` after `priority_label`; `LeadListItemOut` mirror)
- Modify: `apps/web/lib/types.ts` (LeadOut interface)

### Step 1.1 — Write the failing test

- [ ] Append to `apps/api/tests/test_leads_source_enrichment.py`:

```python
def test_lead_out_has_needs_review_field():
    """Sprint 3.7 G3 — schema exposes needs_review flag so the pool UI
    can render the «⚠️ AI создал» pill on auto-created leads."""
    from app.leads.schemas import LeadOut, LeadListItemOut

    assert "needs_review" in LeadOut.model_fields
    assert LeadOut.model_fields["needs_review"].default is False
    assert "needs_review" in LeadListItemOut.model_fields
    assert LeadListItemOut.model_fields["needs_review"].default is False
```

### Step 1.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_leads_source_enrichment.py::test_lead_out_has_needs_review_field -v`
- [ ] Expected: `AssertionError: assert 'needs_review' in [...]` (or `KeyError`).

### Step 1.3 — Add the SQLAlchemy column

- [ ] Open `apps/api/app/leads/models.py`. Find the `assignment_status` column (around line 103). Add this column immediately after it:

```python
    # Sprint 3.7 G3 — AI auto-create safety net. TRUE on leads created
    # by the auto_create_lead_from_email Celery task. Manager confirms
    # (sets FALSE) or soft-deletes the lead from /leads-pool.
    needs_review: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
        default=False,
    )
```

- [ ] Ensure `sa` is already imported at the top of the file (it is — verify with `grep "^import sqlalchemy as sa" apps/api/app/leads/models.py`).

### Step 1.4 — Add the field to Pydantic schemas

- [ ] Open `apps/api/app/leads/schemas.py`. Find `LeadOut` (around line 66) and add right after the existing `priority_label` field:

```python
    # Sprint 3.7 G3 — set TRUE on AI auto-created leads, FALSE everywhere
    # else (form submissions, manual creates, CSV imports, claim-from-pool).
    needs_review: bool = False
```

- [ ] Find `LeadListItemOut` (around line 130) and add the same field at the same position relative to the other fields.

### Step 1.5 — Create the Alembic migration

- [ ] Create `apps/api/alembic/versions/20260519_0031_lead_needs_review.py`:

```python
"""lead_needs_review

Revision ID: 20260519_0031
Revises: 20260516_0030
Create Date: 2026-05-19 14:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260519_0031"
down_revision = "20260516_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "needs_review",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("leads", "needs_review")
```

- [ ] Verify the previous head matches `20260516_0030` with: `ls apps/api/alembic/versions/ | tail -5`. Adjust `down_revision` if a different file is the current head.

### Step 1.6 — Run the test, confirm it passes

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_leads_source_enrichment.py::test_lead_out_has_needs_review_field -v`
- [ ] Expected: PASS.

### Step 1.7 — Update the frontend `LeadOut` interface

- [ ] Open `apps/web/lib/types.ts`. Find `export interface LeadOut` (around line 87). After `latest_utm` (Sprint 3.6 G4 addition), add:

```typescript
  // Sprint 3.7 G3 — TRUE on AI auto-created leads. Surfaced as a pill
  // in /leads-pool with one-click confirm / reject buttons.
  needs_review: boolean;
```

### Step 1.8 — Frontend typecheck

- [ ] Run: `cd apps/web && npm run typecheck`
- [ ] Expected: clean.

### Step 1.9 — Commit

```bash
git add apps/api/alembic/versions/20260519_0031_lead_needs_review.py \
        apps/api/app/leads/models.py \
        apps/api/app/leads/schemas.py \
        apps/api/tests/test_leads_source_enrichment.py \
        apps/web/lib/types.ts
git commit -m "feat(leads): G1 — needs_review column + schema field"
```

---

## Task 2 — Backend: Gate 3 (service local-parts) in route_email

**Files:**
- Modify: `apps/api/app/inbox/processor.py` (constants block + `route_email`)
- Modify: `apps/api/tests/test_inbox_route_email.py`

### Step 2.1 — Write the failing tests

- [ ] Append to `apps/api/tests/test_inbox_route_email.py`:

```python
def test_service_local_part_routes_to_ignore_when_unknown_domain():
    """Gate 3 — info@/support@/news@ from an unknown corporate domain
    is almost always a B2B marketing blast, not a lead. Drop before AI."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="info@unknown-corp.ru",
        subject="Каталог 2026",
        body_preview="Представляем нашу новую линейку...",
        has_known_company=False,
        has_known_contact=False,
    )

    assert decision.route == "ignore"
    assert decision.reason == "service_local_part"


def test_service_local_part_passes_when_known_contact():
    """Override: info@known-customer.ru is still a real client touchpoint
    when the contact is tracked. Gate 3 must NOT block it."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="info@known-customer.ru",
        subject="Re: КП по DrinkX",
        body_preview="Спасибо за коммерческое...",
        has_known_company=True,
        has_known_contact=True,
    )

    assert decision.route == "attach_to_lead"


def test_real_corporate_local_part_passes_gate_3():
    """Personal-name local-parts (not in the service list) reach the
    AI classifier as before — regression guard."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="ivan.petrov@coffee-roastery-zarya.ru",
        subject="Запрос коммерческого предложения",
        body_preview="Здравствуйте, рассматриваем DrinkX...",
        has_known_company=False,
        has_known_contact=False,
    )

    assert decision.route == "inbox"
    assert decision.reason == "unknown_corporate_domain"
```

### Step 2.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_inbox_route_email.py -v -k service_local_part`
- [ ] Expected: 2 tests FAIL with assertion that `decision.reason != "service_local_part"`.

### Step 2.3 — Add the constant + branch

- [ ] Open `apps/api/app/inbox/processor.py`. After the `_NOREPLY_SUBSTRINGS` block (added in PR #50), add:

```python
# Local-parts that are almost always service / marketing addresses on
# unknown corporate domains: catalog blasts, webinar invites, "наши
# спецпредложения" mailings. Override applies when the sender is a
# known contact / known company — then this is a real touchpoint.
_SERVICE_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "info", "support", "hello", "hi", "team",
        "marketing", "news", "newsletter", "contact",
        "press", "media", "events", "webinar", "academy",
        "billing", "invoice", "accounts", "finance",
    }
)
```

- [ ] In `route_email`, insert the new Gate 3 immediately AFTER the noreply-substring branch and BEFORE the unsubscribe-keyword branch:

```python
    # Service local-parts from unknown corporate domains — bulk-mail
    # senders that didn't bother shipping List-Unsubscribe. Known
    # senders are exempt (attach path wins below).
    if local_part in _SERVICE_LOCAL_PARTS and not has_known_contact and not has_known_company:
        return RoutingDecision("ignore", "service_local_part")
```

The variable `local_part` is already in scope from the noreply-substring block (PR #50). If for some reason that block was refactored, compute it locally: `local_part = sender.split("@", 1)[0] if "@" in sender else sender`.

### Step 2.4 — Run, confirm passes

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_inbox_route_email.py -v`
- [ ] Expected: all 12 tests PASS (9 existing from PR #50 + 3 new).

### Step 2.5 — Commit

```bash
git add apps/api/app/inbox/processor.py apps/api/tests/test_inbox_route_email.py
git commit -m "feat(inbox): G2 — Gate 3 service local-parts pre-filter"
```

---

## Task 3 — Backend: Workspace setting `auto_lead_agent_refresh_on_inbound`

**Files:**
- Modify: `apps/api/app/settings/schemas.py` (`AISettingsOut`, `AISettingsUpdateIn`)
- Modify: `apps/api/app/settings/services.py` (`get_ai_settings`, `update_ai_settings`, `_read_ai_section`)
- Modify: `apps/api/app/inbox/message_services.py` (gate `_enqueue_lead_agent_refresh`)
- Create: `apps/api/tests/test_settings_ai_inbound_flag.py`

### Step 3.1 — Write the failing test

- [ ] Create `apps/api/tests/test_settings_ai_inbound_flag.py`:

```python
"""Sprint 3.7 G1 — workspace flag that gates the AI-comment job
fired on matched inbound. Default OFF so Layer 1 is truly no-LLM."""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_ai_settings_out_exposes_inbound_flag():
    from app.settings.schemas import AISettingsOut

    assert "auto_lead_agent_refresh_on_inbound" in AISettingsOut.model_fields
    # Default OFF — Layer 1 is no-LLM by default.
    default = AISettingsOut.model_fields[
        "auto_lead_agent_refresh_on_inbound"
    ].default
    assert default is False


def test_ai_settings_update_in_accepts_flag():
    from app.settings.schemas import AISettingsUpdateIn

    assert "auto_lead_agent_refresh_on_inbound" in AISettingsUpdateIn.model_fields
    # Optional on PATCH — None means "leave as-is".
    body = AISettingsUpdateIn(auto_lead_agent_refresh_on_inbound=True)
    assert body.auto_lead_agent_refresh_on_inbound is True
```

### Step 3.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_settings_ai_inbound_flag.py -v`
- [ ] Expected: `AssertionError: 'auto_lead_agent_refresh_on_inbound' not in [...]`.

### Step 3.3 — Add field to schemas

- [ ] Open `apps/api/app/settings/schemas.py`. Append to `AISettingsOut` (after `available_models`):

```python
    # Sprint 3.7 G1 — when TRUE, matched inbound emails fire a Чак
    # comment refresh via _enqueue_lead_agent_refresh. Default OFF so
    # Layer 1 (auto-attach) is truly no-LLM by default.
    auto_lead_agent_refresh_on_inbound: bool = False
```

- [ ] Append to `AISettingsUpdateIn`:

```python
    # Sprint 3.7 G1 — toggle for the Чак-comment-on-inbound job.
    auto_lead_agent_refresh_on_inbound: bool | None = None
```

### Step 3.4 — Resolve the value in `get_ai_settings`

- [ ] Open `apps/api/app/settings/services.py`. In `get_ai_settings` (around line 68), update the read block to include the new field. The function returns a dict; add:

```python
    auto_refresh = bool(ai.get("auto_lead_agent_refresh_on_inbound", False))
```

  ...alongside the existing `daily_budget` and `primary_model` reads. Then include `auto_refresh` in the returned dict:

```python
    return {
        "daily_budget_usd": daily_budget,
        "primary_model": primary_model,
        "current_spend_usd_today": float(spend),
        "available_models": list(AI_MODEL_CHOICES),
        "auto_lead_agent_refresh_on_inbound": auto_refresh,
    }
```

### Step 3.5 — Persist the value in `update_ai_settings`

- [ ] Still in `apps/api/app/settings/services.py`. Extend `update_ai_settings` signature with the new optional kwarg:

```python
async def update_ai_settings(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    daily_budget_usd: float | None = None,
    primary_model: str | None = None,
    auto_lead_agent_refresh_on_inbound: bool | None = None,
) -> dict:
```

- [ ] In the same function, after the existing handling of `daily_budget_usd` / `primary_model`, add:

```python
    if auto_lead_agent_refresh_on_inbound is not None:
        ai["auto_lead_agent_refresh_on_inbound"] = bool(
            auto_lead_agent_refresh_on_inbound
        )
```

### Step 3.6 — Wire the router PATCH handler

- [ ] Open `apps/api/app/settings/routers.py`. Find the AI settings PATCH handler (around line 119). The handler reads `body.daily_budget_usd` / `body.primary_model` — add the new field to the kwargs passed to `svc.update_ai_settings(...)`:

```python
    result = await svc.update_ai_settings(
        db,
        workspace_id=user.workspace_id,
        daily_budget_usd=body.daily_budget_usd,
        primary_model=body.primary_model,
        auto_lead_agent_refresh_on_inbound=body.auto_lead_agent_refresh_on_inbound,
    )
```

### Step 3.7 — Gate the inbound AI-comment job

- [ ] Open `apps/api/app/inbox/message_services.py`. Find the call to `_enqueue_lead_agent_refresh` (around line 221). Wrap it in a workspace-setting check. Before the call, resolve the flag:

```python
            # Sprint 3.7 G1 — gate the optional AI-comment refresh
            # behind a workspace setting. Default OFF so matched inbound
            # is truly no-LLM unless an admin opts in.
            from app.auth.models import Workspace as _Workspace

            ws_res = await session.execute(
                select(_Workspace).where(_Workspace.id == workspace_id)
            )
            ws = ws_res.scalar_one_or_none()
            ai_block = (ws.settings_json or {}).get("ai", {}) if ws else {}
            if bool(ai_block.get("auto_lead_agent_refresh_on_inbound", False)):
                _enqueue_lead_agent_refresh(lead_id, countdown=900)
```

Replace the existing unconditional `_enqueue_lead_agent_refresh(lead_id, countdown=900)` with the gated block above.

### Step 3.8 — Run, confirm passes

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_settings_ai_inbound_flag.py tests/test_inbox_route_email.py -v`
- [ ] Expected: 2 new tests PASS + 12 from Task 2 PASS.

### Step 3.9 — Commit

```bash
git add apps/api/app/settings/schemas.py apps/api/app/settings/services.py \
        apps/api/app/settings/routers.py apps/api/app/inbox/message_services.py \
        apps/api/tests/test_settings_ai_inbound_flag.py
git commit -m "feat(settings,inbox): G1 — gate inbound Чак-refresh behind workspace flag"
```

---

## Task 4 — Backend: `auto_create_lead_from_email` Celery task

**Files:**
- Modify: `apps/api/app/scheduled/jobs.py` (replace `generate_inbox_suggestion` + `_run_inbox_suggestion`)
- Modify: `apps/api/app/inbox/processor.py` (lines 522-551 — replace InboxItem-write-then-enqueue with direct enqueue)
- Create: `apps/api/tests/test_auto_create_lead_from_email.py`

### Step 4.1 — Write the failing tests

- [ ] Create `apps/api/tests/test_auto_create_lead_from_email.py`:

```python
"""Sprint 3.7 G3 — auto_create_lead_from_email task core."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_low_confidence_drops_silently():
    """confidence < 0.85 → no DB writes, no LLM follow-up."""
    from app.scheduled import jobs as j

    workspace_id = uuid.uuid4()
    fake_llm = AsyncMock(return_value=MagicMock(
        text='{"action": "create_lead", "company_name": "X", '
             '"contact_name": "Y", "confidence": 0.7}',
        cost_usd=0.0,
    ))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock()) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=workspace_id,
                channel_user_id=uuid.uuid4(),
                from_email="ivan@unknown.ru",
                subject="X",
                body_preview="Y",
                gmail_message_id="g-1",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_not_awaited()
    assert out["action"] == "ignore_low_confidence"


@pytest.mark.asyncio
async def test_ignore_action_drops_silently():
    """confidence ≥ 0.85 but action=='ignore' → no DB writes."""
    from app.scheduled import jobs as j

    fake_llm = AsyncMock(return_value=MagicMock(
        text='{"action": "ignore", "company_name": "", '
             '"contact_name": "", "confidence": 0.95}',
        cost_usd=0.0,
    ))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock()) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=uuid.uuid4(),
                channel_user_id=uuid.uuid4(),
                from_email="event@some-conference.ru",
                subject="Welcome",
                body_preview="...",
                gmail_message_id="g-2",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_not_awaited()
    assert out["action"] == "ignore_ai"


@pytest.mark.asyncio
async def test_high_confidence_create_lead_fires_factory():
    """confidence ≥ 0.85 AND action='create_lead' → factory invoked."""
    from app.scheduled import jobs as j

    fake_llm = AsyncMock(return_value=MagicMock(
        text='{"action": "create_lead", "company_name": "Coffee Zarya", '
             '"contact_name": "Ivan Petrov", "confidence": 0.92}',
        cost_usd=0.0,
    ))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock(
        return_value=uuid.uuid4()
    )) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=uuid.uuid4(),
                channel_user_id=uuid.uuid4(),
                from_email="ivan@coffee-zarya.ru",
                subject="Запрос КП",
                body_preview="Интересует пилот DrinkX",
                gmail_message_id="g-3",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_awaited_once()
    assert out["action"] == "lead_created"
    assert out["confidence"] == 0.92


@pytest.mark.asyncio
async def test_llm_failure_drops_silently():
    """Any LLMError / parse failure → no DB writes, no exception out."""
    from app.scheduled import jobs as j
    from app.enrichment.providers.base import LLMError

    fake_llm = AsyncMock(side_effect=LLMError("boom", provider="mimo"))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock()) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=uuid.uuid4(),
                channel_user_id=uuid.uuid4(),
                from_email="ivan@coffee-zarya.ru",
                subject="X",
                body_preview="Y",
                gmail_message_id="g-4",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_not_awaited()
    assert out["action"] == "ignore_llm_error"
```

### Step 4.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_auto_create_lead_from_email.py -v`
- [ ] Expected: 4 tests FAIL with `AttributeError: module 'app.scheduled.jobs' has no attribute '_run_auto_create_or_ignore'`.

### Step 4.3 — Replace the Celery task in `jobs.py`

- [ ] Open `apps/api/app/scheduled/jobs.py`. Replace the existing `generate_inbox_suggestion` task and its async core `_run_inbox_suggestion` (lines 68-280) with the new task. Keep the existing `_INBOX_SUGGESTION_SYSTEM` and `_INBOX_SUGGESTION_USER` prompts — same prompt, different output handler.

Replace the entire block from `@celery_app.task(name="app.scheduled.jobs.generate_inbox_suggestion")` through the end of `_run_inbox_suggestion` with:

```python
@celery_app.task(name="app.scheduled.jobs.auto_create_lead_from_email")
def auto_create_lead_from_email(
    workspace_id: str,
    channel_user_id: str,
    from_email: str,
    subject: str,
    body_preview: str,
    gmail_message_id: str,
    received_at_iso: str,
) -> dict:
    """Sprint 3.7 G3 — AI prefilter for an unmatched email.

    Decides: silent drop OR create Lead with needs_review=True.
    No InboxItem row is written under any branch — manager triage
    happens in /leads-pool, not /inbox.
    """
    return asyncio.run(
        _run_auto_create_or_ignore(
            workspace_id=UUID(workspace_id),
            channel_user_id=UUID(channel_user_id),
            from_email=from_email,
            subject=subject,
            body_preview=body_preview,
            gmail_message_id=gmail_message_id,
            received_at_iso=received_at_iso,
        )
    )


# Confidence threshold — auto-create only above this number. Below the
# threshold the email disappears silently. 0.85 was chosen so a false
# positive needs the AI to be both highly confident AND wrong; tighten
# (or loosen) once we have a feedback loop.
_AUTO_CREATE_CONFIDENCE_THRESHOLD = 0.85


async def _run_auto_create_or_ignore(
    *,
    workspace_id: UUID,
    channel_user_id: UUID,
    from_email: str,
    subject: str,
    body_preview: str,
    gmail_message_id: str,
    received_at_iso: str,
) -> dict:
    """Best-effort auto-create. Never raises.

    Flow:
      1. Ask the AI classifier (same prompt as the old
         `generate_inbox_suggestion`).
      2. If confidence < threshold OR action != "create_lead" → drop.
      3. Otherwise materialise Company + Contact + Lead + Activity in
         one transaction via `_create_lead_from_email_payload`.
    """
    import json as _json

    from app.enrichment.providers.base import LLMError, TaskType
    from app.enrichment.providers.factory import complete_with_fallback

    user_prompt = _INBOX_SUGGESTION_USER.format(
        from_email=from_email or "",
        subject=subject or "",
        body_preview=(body_preview or "")[:500],
    )
    try:
        completion = await complete_with_fallback(
            system=_INBOX_SUGGESTION_SYSTEM,
            user=user_prompt,
            task_type=TaskType.prefilter,
            max_tokens=200,
            temperature=0.2,
        )
    except LLMError as exc:
        log.warning(
            "auto_create.llm_failed",
            from_email=from_email,
            error=str(exc)[:200],
        )
        return {
            "job": "auto_create_lead_from_email",
            "action": "ignore_llm_error",
        }

    try:
        cleaned = _json.loads(completion.text or "{}")
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "auto_create.parse_failed",
            from_email=from_email,
            error=str(exc)[:200],
        )
        return {
            "job": "auto_create_lead_from_email",
            "action": "ignore_parse_error",
        }

    confidence = float(cleaned.get("confidence") or 0.0)
    action = str(cleaned.get("action") or "ignore")

    if confidence < _AUTO_CREATE_CONFIDENCE_THRESHOLD:
        return {
            "job": "auto_create_lead_from_email",
            "action": "ignore_low_confidence",
            "confidence": confidence,
        }
    if action != "create_lead":
        return {
            "job": "auto_create_lead_from_email",
            "action": "ignore_ai",
            "ai_action": action,
        }

    try:
        lead_id = await _create_lead_from_email_payload(
            workspace_id=workspace_id,
            channel_user_id=channel_user_id,
            company_name=str(cleaned.get("company_name") or "").strip(),
            contact_name=str(cleaned.get("contact_name") or "").strip(),
            from_email=from_email,
            subject=subject,
            body_preview=body_preview,
            gmail_message_id=gmail_message_id,
            received_at_iso=received_at_iso,
            confidence=confidence,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "auto_create.factory_failed",
            from_email=from_email,
            error=str(exc)[:200],
        )
        return {
            "job": "auto_create_lead_from_email",
            "action": "ignore_factory_error",
        }

    return {
        "job": "auto_create_lead_from_email",
        "action": "lead_created",
        "lead_id": str(lead_id),
        "confidence": confidence,
    }


async def _create_lead_from_email_payload(
    *,
    workspace_id: UUID,
    channel_user_id: UUID,
    company_name: str,
    contact_name: str,
    from_email: str,
    subject: str,
    body_preview: str,
    gmail_message_id: str,
    received_at_iso: str,
    confidence: float,
) -> UUID:
    """Materialise Company + Contact + Lead + Activity in one transaction.

    Idempotent on `gmail_message_id` — if an Activity already references
    this id, return the existing lead and skip creation.
    """
    from datetime import datetime
    from sqlalchemy import select

    from app.activity.models import Activity
    from app.companies.models import Company
    from app.contacts.models import Contact
    from app.leads.models import Lead
    from app.pipelines import repositories as pipelines_repo

    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            # Idempotency check
            existing = await session.execute(
                select(Activity.lead_id)
                .where(Activity.gmail_message_id == gmail_message_id)
                .limit(1)
            )
            prior = existing.scalar_one_or_none()
            if prior is not None:
                return prior

            # 1. Domain → Company (find or create)
            domain = (from_email.split("@", 1)[1] if "@" in from_email else "").lower().strip()
            company_id: UUID | None = None
            if domain:
                row = await session.execute(
                    select(Company.id).where(
                        Company.workspace_id == workspace_id,
                        Company.domain == domain,
                    ).limit(1)
                )
                company_id = row.scalar_one_or_none()
            if company_id is None:
                company = Company(
                    workspace_id=workspace_id,
                    name=(company_name or domain or from_email)[:255],
                    domain=domain or None,
                )
                session.add(company)
                await session.flush()
                company_id = company.id

            # 2. Email → Contact (find or create)
            row = await session.execute(
                select(Contact.id).where(
                    Contact.workspace_id == workspace_id,
                    Contact.email == from_email.lower(),
                ).limit(1)
            )
            contact_id = row.scalar_one_or_none()
            if contact_id is None:
                contact = Contact(
                    workspace_id=workspace_id,
                    company_id=company_id,
                    name=(contact_name or from_email.split("@", 1)[0])[:255],
                    email=from_email.lower(),
                    source="auto_email",
                )
                session.add(contact)
                await session.flush()
                contact_id = contact.id

            # 3. Resolve target pipeline + first stage
            first = await pipelines_repo.get_default_first_stage(
                session, workspace_id
            )
            pipeline_id, stage_id = (first or (None, None))

            # 4. Lead
            lead = Lead(
                workspace_id=workspace_id,
                pipeline_id=pipeline_id,
                stage_id=stage_id,
                company_id=company_id,
                primary_contact_id=contact_id,
                company_name=(company_name or domain or from_email)[:255],
                email=from_email.lower(),
                assignment_status="pool",
                tags_json=[],
                source="auto_email",
                needs_review=True,
                ai_data={"auto_create_confidence": confidence},
            )
            session.add(lead)
            await session.flush()
            lead_id = lead.id

            # 5. Activity row
            received_at = datetime.fromisoformat(received_at_iso)
            session.add(
                Activity(
                    lead_id=lead_id,
                    user_id=None,
                    type="email",
                    direction="inbound",
                    body=body_preview,
                    subject=subject,
                    from_identifier=from_email,
                    gmail_message_id=gmail_message_id,
                    received_at=received_at,
                    payload_json={"confidence": confidence},
                )
            )

            await session.commit()
            return lead_id
    finally:
        await engine.dispose()
```

- [ ] Verify the module top still has these imports (add if missing):

```python
import asyncio
import structlog
from uuid import UUID

log = structlog.get_logger()
```

### Step 4.4 — Update the caller in `processor.py`

- [ ] Open `apps/api/app/inbox/processor.py`. Find the `InboxItem` create + dispatch block (lines 522-551 ish — the path that runs when `decision.route == "inbox"`). Replace it with:

```python
        # ---- inbox (or attach-fallback) --------------------------------------
        # Sprint 3.7 G3: no InboxItem row is written. The Celery task
        # carries the payload directly and decides drop-vs-auto-create
        # from the AI verdict. Manager triage happens in /leads-pool
        # via the needs_review pill, not on a separate /inbox page.
        try:
            from app.scheduled.celery_app import celery_app

            celery_app.send_task(
                "app.scheduled.jobs.auto_create_lead_from_email",
                args=[
                    str(workspace_id),
                    str(user_id),
                    from_email or "",
                    subject or "",
                    body_preview or "",
                    gmail_message_id,
                    received_at.isoformat() if received_at else "",
                ],
            )
        except Exception as exc:
            bound_log.warning(
                "inbox.auto_create_dispatch_failed",
                gmail_message_id=gmail_message_id,
                error=str(exc)[:200],
            )

        bound_log.info(
            "inbox.process_message.dispatched_auto_create",
            gmail_message_id=gmail_message_id,
            route_reason=decision.reason,
        )
        return True
```

- [ ] Delete the now-orphaned `InboxItem(...)` instantiation that lived above the old `send_task` call. The `InboxItem` import at the top of `processor.py` may also become unused — remove it if so (typecheck will flag if anything else still uses it).

### Step 4.5 — Run tests

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_auto_create_lead_from_email.py tests/test_inbox_route_email.py -v`
- [ ] Expected: 4 new tests PASS + 12 from Task 2 PASS. The pre-existing `test_inbox_matcher.py::test_processor_creates_activity_on_high_confidence_match` failure on `main` (AsyncMock setup) is NOT in scope here — do not try to fix.

### Step 4.6 — Commit

```bash
git add apps/api/app/scheduled/jobs.py apps/api/app/inbox/processor.py \
        apps/api/tests/test_auto_create_lead_from_email.py
git commit -m "feat(inbox,scheduled): G3 — auto_create_lead_from_email Celery task"
```

---

## Task 5 — Backend: `needs_review` filter on /leads/pool

**Files:**
- Modify: `apps/api/app/leads/repositories.py` (`list_pool`)
- Modify: `apps/api/app/leads/routers.py` (pool endpoint Query param)
- Modify: `apps/api/tests/test_leads_source_enrichment.py`

### Step 5.1 — Write the failing test

- [ ] Append to `apps/api/tests/test_leads_source_enrichment.py`:

```python
@pytest.mark.asyncio
async def test_list_pool_needs_review_filter_applies():
    """list_pool with needs_review=True must add the column filter and
    proceed to count + list queries (no short-circuit)."""
    from app.leads import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one=lambda: 0),  # count
            MagicMock(all=lambda: []),  # list — empty after filter
        ]
    )

    rows, total = await repo.list_pool(
        db,
        workspace_id=uuid.uuid4(),
        needs_review=True,
    )

    assert rows == []
    assert total == 0
    assert db.execute.await_count >= 2
```

### Step 5.2 — Run, confirm failure

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_leads_source_enrichment.py::test_list_pool_needs_review_filter_applies -v`
- [ ] Expected: `TypeError: list_pool() got an unexpected keyword argument 'needs_review'`.

### Step 5.3 — Add the filter

- [ ] Open `apps/api/app/leads/repositories.py`. In `list_pool`, add `needs_review: bool | None = None` to the signature. After the existing filter chain (alongside `city`, `segment`, etc.), add:

```python
    if needs_review is True:
        base = base.where(Lead.needs_review.is_(True))
    elif needs_review is False:
        base = base.where(Lead.needs_review.is_(False))
```

### Step 5.4 — Add the router Query param

- [ ] Open `apps/api/app/leads/routers.py`. Find the `/leads/pool` handler. Add `needs_review: bool | None = Query(None)` to the signature. Pass it into the `filters` dict (mirrors Sprint 3.6 G2 `form_id` pattern).

### Step 5.5 — Run the test

- [ ] Run: `cd apps/api && .venv/bin/pytest tests/test_leads_source_enrichment.py -v`
- [ ] Expected: all existing tests PASS + 1 new PASS.

### Step 5.6 — Commit

```bash
git add apps/api/app/leads/repositories.py apps/api/app/leads/routers.py \
        apps/api/tests/test_leads_source_enrichment.py
git commit -m "feat(leads): G4 — needs_review filter on /leads/pool"
```

---

## Task 6 — Frontend: `needs_review` filter + pill UI on /leads-pool

**Files:**
- Modify: `apps/web/lib/hooks/use-leads.ts` (`usePoolLeads` accepts new filter)
- Create: `apps/web/components/leads-pool/NeedsReviewRow.tsx`
- Modify: `apps/web/app/(app)/leads-pool/page.tsx` (filter chip + per-row pill)

### Step 6.1 — Add `needs_review` to the pool filter

- [ ] Open `apps/web/lib/hooks/use-leads.ts`. Find the pool filter type (the `usePoolLeads` arg type — likely an interface near the hook). Add `needs_review?: boolean`. Mirror the `form_id` query-string-builder line for `needs_review`:

```typescript
if (filters.needs_review !== undefined) p.set("needs_review", String(filters.needs_review));
```

### Step 6.2 — Create the pill + actions component

- [ ] Create `apps/web/components/leads-pool/NeedsReviewRow.tsx`:

```tsx
"use client";

import { Sparkles } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { LeadOut } from "@/lib/types";

interface Props {
  lead: LeadOut;
  onSoftDelete: () => void; // open the existing delete-confirm modal
}

/**
 * Sprint 3.7 G4 — pill + two-button tray surfaced on leads with
 * `needs_review=true`. «Подтвердить» clears the flag; «Не лид» fires
 * the parent's soft-delete confirm flow.
 */
export function NeedsReviewRow({ lead, onSoftDelete }: Props) {
  const qc = useQueryClient();
  const confidence = Number(
    (lead.ai_data as Record<string, unknown> | null)?.auto_create_confidence ?? 0,
  );
  const percent = Math.round(confidence * 100);

  const confirm = useMutation({
    mutationFn: () =>
      api.patch(`/leads/${lead.id}`, { needs_review: false }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
    },
  });

  return (
    <div className="mt-1 flex items-center gap-2 flex-wrap">
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-amber-700 bg-amber-50 border border-amber-200"
        title="AI создал этого лида автоматически из входящего письма"
      >
        <Sparkles size={10} aria-hidden />
        AI создал · {percent}%
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          confirm.mutate();
        }}
        disabled={confirm.isPending}
        className="text-[11px] px-2 py-0.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        Подтвердить
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onSoftDelete();
        }}
        className="text-[11px] px-2 py-0.5 rounded text-rose-700 bg-rose-50 hover:bg-rose-100"
      >
        Не лид
      </button>
    </div>
  );
}
```

### Step 6.3 — Verify `api.patch` exists

- [ ] Run: `grep -n "patch:" apps/web/lib/api-client.ts` — confirm a `.patch` method exists. If not, locate the actual PATCH method name (likely `api.update` or `api.put`) and adapt the snippet above.

### Step 6.4 — Wire into /leads-pool

- [ ] Open `apps/web/app/(app)/leads-pool/page.tsx`. In the row render (where the per-row source chip from Sprint 3.6 G6 lives), add immediately after the existing chip block:

```tsx
{lead.needs_review && (
  <NeedsReviewRow
    lead={lead}
    onSoftDelete={() => setConfirmDelete(lead)}
  />
)}
```

- [ ] Import: `import { NeedsReviewRow } from "@/components/leads-pool/NeedsReviewRow";`
- [ ] If `setConfirmDelete` doesn't yet exist (the delete-confirm flow may already use a different name), reuse whatever modal trigger is already in the file for «Удалить лид» / «Не лид».

### Step 6.5 — Add the «Только AI-созданные» filter chip

- [ ] In the same file, in the filter bar area (where the «Источник» dropdown from Sprint 3.6 lives), add a toggle button:

```tsx
<button
  type="button"
  onClick={() => setNeedsReview((v) => (v === true ? undefined : true))}
  className={`text-[11px] px-2 py-1 rounded ${
    needsReview === true
      ? "bg-amber-600 text-white"
      : "bg-canvas border border-black/5 text-muted-2 hover:border-amber-400"
  }`}
>
  Только AI-созданные
</button>
```

- [ ] Add a `useState<boolean | undefined>(undefined)` for `needsReview` near the existing filter state. Pass `needs_review: needsReview` into `usePoolLeads({...})`.

### Step 6.6 — Build + visual verification

- [ ] Run: `cd apps/web && npm run typecheck && npm run lint && pnpm build`
- [ ] Expected: typecheck clean, lint baseline (21 warnings), build green.
- [ ] Locally: open `/leads-pool`, click «Только AI-созданные» — the list should filter to leads where `needs_review=true`. Click «Подтвердить» on one of those leads — the pill should disappear (cache invalidates).

### Step 6.7 — Commit

```bash
git add apps/web/lib/hooks/use-leads.ts \
        apps/web/components/leads-pool/NeedsReviewRow.tsx \
        apps/web/app/\(app\)/leads-pool/page.tsx
git commit -m "feat(leads-pool): G4 — needs_review pill + confirm/reject buttons"
```

---

## Task 7 — Frontend: tear out /inbox page

**Files:**
- Delete: `apps/web/app/(app)/inbox/page.tsx` (and the directory if empty after)
- Modify: `apps/web/components/layout/SidebarNavContainer.tsx` (remove «Входящие» item + badge)
- Read first: `apps/web/components/inbox/UnmatchedMessagesSection.tsx` — relocate, do NOT delete

### Step 7.1 — Confirm UnmatchedMessagesSection's scope

- [ ] Read `apps/web/components/inbox/UnmatchedMessagesSection.tsx`. The Sprint 3.4 component lists unmatched **Telegram / MAX / Phone** messages (it does NOT touch Gmail). Confirm this by reading its `useInboxUnmatchedMessages` hook source.
- [ ] Decide where to relocate it. Recommended: render it as a widget on `/today` (it's a short list of unmatched messenger threads needing manual assign-to-lead). If you prefer a separate route, create `apps/web/app/(app)/triage/page.tsx` that just renders the component.
- [ ] Apply the chosen relocation.

### Step 7.2 — Delete the /inbox page

- [ ] Run: `rm apps/web/app/\(app\)/inbox/page.tsx`
- [ ] Run: `rmdir apps/web/app/\(app\)/inbox` (will succeed only if the directory is empty — fine if it errors).

### Step 7.3 — Remove «Входящие» from the sidebar

- [ ] Open `apps/web/components/layout/SidebarNavContainer.tsx`. Find the `inbox` nav item entry (around lines 50-60 — `{ id: "inbox", label: "Входящие", href: "/inbox", icon: <Inbox ... /> ... }`). Delete the entire object.
- [ ] Remove the `useInboxCount` hook call if it has no other consumer in this file. Same for the `Inbox` lucide import if it's now orphaned.

### Step 7.4 — Audit dead backend routes

- [ ] Run: `grep -rn "inbox_items_confirm\|inbox/items/.*confirm\|inbox/items/.*dismiss\|inbox/pending" apps/api 2>/dev/null`
- [ ] For each endpoint that exists ONLY for the deleted /inbox page (the manager confirm/dismiss flow on `InboxItem`), remove the route. Keep the `InboxItem` model and the messenger-unmatched routes — they serve `UnmatchedMessagesSection`'s Telegram/MAX/Phone data, which is a different concern.
- [ ] Leave a stub `# Sprint 3.7: /inbox Gmail triage retired. InboxItem model kept for audit.` comment near the removed routes for archaeology.

### Step 7.5 — Build + verification

- [ ] Run: `cd apps/web && npm run typecheck && npm run lint && pnpm build`
- [ ] Expected: typecheck clean, lint baseline, build green. `/inbox` no longer appears in the build manifest.
- [ ] Locally: confirm `/inbox` returns Next's 404 and the sidebar shows no «Входящие» row.

### Step 7.6 — Commit

```bash
git add -A
git commit -m "feat(inbox,web): G5 — retire /inbox triage page + sidebar entry"
```

---

## Task 8 — Docs: manager-facing email-workflow guide

**Files:**
- Create: `docs/email-workflow.md`

### Step 8.1 — Write the docs

- [ ] Create `docs/email-workflow.md`:

```markdown
# Как работает почта в CRM

## TL;DR

Почта существует, чтобы лиды в CRM сами обогащались перепиской. Никакого
отдельного «inbox-zero» в CRM нет — менеджер живёт в Lead Card и в Pool.

## Что происходит, когда приходит письмо

1. **От известного контакта или с известного домена** — письмо
   автоматически попадает в «Активность» / «Переписку» соответствующего
   лида. Никакого AI, никакого подтверждения.
2. **От незнакомого корпоративного адреса** — AI быстро оценивает «это
   потенциальный B2B клиент?». Если уверенность ≥ 85% и письмо похоже
   на коммерческое обращение — автоматически создаётся лид в Pool с
   пометкой «⚠️ AI создал · 87%».
3. **Всё остальное** (рассылки, billing, личное, спам) — тихо игнорируется.

## Что делает менеджер

- Каждое утро открывает «Сегодня» — Чак показывает приоритетные задачи.
- Открывает лид → вкладка «Активность» содержит новые письма с
  таймстампом.
- Раз в день заходит в Pool, фильтр «Только AI-созданные» — видит лидов,
  которых AI добавил. По каждому: «Подтвердить» (нормальный лид) или
  «Не лид» (soft-delete).
- Отвечает на письма из обычной Gmail-почты. Ответы CRM подхватывает
  автоматически через email-thread.

## Что НЕ делает менеджер

- Не разбирает «неразобранное» (нет такого раздела).
- Не получает уведомления о рассылках от PlayStation / Substack / iiko
  Academy — они отсекаются на уровне инфраструктуры.

## Как отключить (если не нравится)

Раздел Settings → AI:

- **«AI комментирует входящие»** (default OFF) — если включить, Чак
  будет добавлять короткий комментарий к каждому новому письму на лиде
  («Алексей упомянул закрытие теста»). Стоит токены, но даёт быстрый
  контекст.
- AI auto-create порог 85% жёстко зашит — менять не нужно. Если AI
  создаёт мусорных лидов, жми «Не лид» — со временем добавим feedback
  loop.

## Что НЕ работает (out of scope)

- Отправка писем из CRM напрямую — отвечайте из Gmail.
- Множественные ящики на одного менеджера — один Gmail per manager.
- Парсинг писем-форм — для заявок с лендингов используется `/forms`.
```

### Step 8.2 — Commit

```bash
git add docs/email-workflow.md
git commit -m "docs: G6 — manager-facing email workflow guide"
```

---

## Task 9 — Smoke verification on staging / local

**Files:** none (manual verification + spec checklist tick).

### Step 9.1 — Smoke each scenario

- [ ] **Auto-attach (Layer 1)** — send a Gmail to a known contact's address. Verify in `/leads/{id}?tab=activity` that the email appears within ~30s. Check API logs to confirm `_enqueue_lead_agent_refresh` was NOT called (Layer 1 is no-LLM by default).
- [ ] **Gate 1** — send from `noreply@*` to a managed inbox. Verify the email is silently dropped (no lead, no activity). API logs show `route_email` returning `("ignore", "noreply_sender")`.
- [ ] **Gate 3 (Sprint 3.7 G2)** — send from `info@some-unknown-corp.ru` with «Каталог 2026» subject. Verify it's silently dropped with reason `service_local_part`.
- [ ] **Gate 4 success** — send from `ivan.petrov@new-coffee-roastery.ru` with «Запрос коммерческого предложения DrinkX, рассматриваем пилот» body. Verify a Lead lands in Pool with `needs_review=true` and the «AI создал · NN%» pill. Verify the email is on the Activity tab.
- [ ] **Gate 4 low confidence** — send from `alex@some-org.ru` with «Доброго дня, у меня вопрос» (deliberately ambiguous). Verify it's silently dropped (no lead created).
- [ ] **Confirm flow** — click «Подтвердить» on the auto-created lead. Verify the pill disappears and the lead behaves like a normal pool lead.
- [ ] **Reject flow** — auto-create another lead via Gate 4. Click «Не лид» → confirm modal → submit. Verify the lead is soft-deleted (`assignment_status=deleted` in DB).
- [ ] **Settings toggle** — flip «AI комментирует входящие» ON. Send a known-contact email. Verify a Чак comment appears on the lead's activity feed within ~10 minutes (the existing `countdown=900` delay).
- [ ] **404 on /inbox** — visit `/inbox`. Expect a 404 page.
- [ ] **Sidebar audit** — no «Входящие» entry visible.

### Step 9.2 — Update the sprint spec checklist

- [ ] Open `docs/SPRINT_3_7_EMAIL_WORKFLOW_SIMPLIFICATION.md`. Tick each smoke checklist item that passed.

### Step 9.3 — Commit

```bash
git add docs/SPRINT_3_7_EMAIL_WORKFLOW_SIMPLIFICATION.md
git commit -m "docs(sprint-3.7): smoke run verified"
```

---

## Final — Push + PR

### Step F.1 — Push the branch

```bash
git push -u origin sprint/3.7-email-workflow
```

### Step F.2 — Open the PR

```bash
gh pr create --title "Sprint 3.7 — Email Workflow Simplification" --body "..."
```

PR description follows the Sprint 3.5 / 3.6 template: summary, gate-by-gate
recap, test plan checklist. Reference the spec at
`docs/SPRINT_3_7_EMAIL_WORKFLOW_SIMPLIFICATION.md`.

---

## Self-review notes (2026-05-19)

- **Spec coverage:** G1–G6 of the spec map to Tasks 1–8 (T1: schema +
  column for needs_review; T2: Gate 3 service local-parts; T3: workspace
  flag + gating; T4: replace Celery task; T5: pool filter; T6: frontend
  pill + filter chip; T7: tear out /inbox; T8: docs).
- **Placeholder scan:** No TBDs. Each step has either the exact code or
  the exact command. The relocation decision for `UnmatchedMessagesSection`
  is the only place an implementer has to make a judgement call — but
  the spec resolves it (either `/today` widget OR new `/triage` route)
  with a clear default.
- **Type consistency:** `needs_review` named consistently across SQL
  column, Pydantic field, TypeScript field, query param, and React prop.
  `auto_lead_agent_refresh_on_inbound` named consistently across the
  schemas, the settings store key, and the gate in `message_services.py`.
  `auto_create_lead_from_email` Celery task name + `_run_auto_create_or_ignore`
  async core consistent between Task 4's signature and Task 4's caller in
  `processor.py`.
- **Out-of-scope adherence:** No Gmail send (Layer 3), no mailbox-as-source
  rules, no multi-mailbox support, no parser-from-email — all per spec.
