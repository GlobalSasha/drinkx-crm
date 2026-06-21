"""Manager workload — role-aware assignee scoping for GET /leads."""
from __future__ import annotations

import sys
import uuid

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

# `_stub_sqlalchemy` doesn't register `defer` on the sqlalchemy.orm stub, but
# app/leads/repositories.py imports it.  Add a no-op stand-in so the import
# chain doesn't blow up before we reach _resolve_assignee_scope.
_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    _sa_orm.defer = lambda *a, **kw: None  # type: ignore[attr-defined]


def test_scope_admin_all_assignees_returns_none():
    from app.leads.routers import _resolve_assignee_scope
    u = uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=True, q=None, user_id=u, role="admin"
    ) is None


def test_scope_head_explicit_returns_that_manager():
    from app.leads.routers import _resolve_assignee_scope
    me, other = uuid.uuid4(), uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=other, all_assignees=False, q=None, user_id=me, role="head"
    ) == other


def test_scope_admin_default_returns_self():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q=None, user_id=me, role="admin"
    ) == me


def test_scope_regular_explicit_id_is_honored():
    # B2: ?assigned_to=<id> from a regular manager is now honored so they
    # can view a single user's book ('just mine' or a colleague's), instead
    # of being forced back to self.
    from app.leads.routers import _resolve_assignee_scope
    me, other = uuid.uuid4(), uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=other, all_assignees=True, q=None, user_id=me, role="manager"
    ) == other


def test_scope_regular_default_is_whole_workspace():
    # B2: a regular manager with no ?assigned_to now sees ALL workspace
    # leads (None = no assignee filter), not just their own.
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q=None, user_id=me, role="manager"
    ) is None


def test_scope_picker_optin_is_whole_workspace():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    # the message-to-lead picker opts in via workspace_search → whole workspace
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q="кофейня", user_id=me, role="manager",
        workspace_search=True,
    ) is None


def test_scope_regular_q_without_optin_is_whole_workspace():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    # B2: with the open default, a manager's kanban search (no
    # workspace_search opt-in, no explicit ?assigned_to) is whole-workspace
    # too — the q carve-out no longer matters because the default is None.
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q="кофейня", user_id=me, role="manager",
        workspace_search=False,
    ) is None


def test_scope_regular_q_with_optin_is_whole_workspace():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    # the picker opts in → whole-workspace search, as before
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q="кофейня", user_id=me, role="manager",
        workspace_search=True,
    ) is None


def test_scope_admin_q_with_explicit_keeps_manager():
    from app.leads.routers import _resolve_assignee_scope
    me, other = uuid.uuid4(), uuid.uuid4()
    # admin searching within a specific manager's book → keep that manager
    assert _resolve_assignee_scope(
        explicit=other, all_assignees=False, q="кофейня", user_id=me, role="head"
    ) == other


def test_scope_admin_q_without_explicit_is_whole_workspace():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q="кофейня", user_id=me, role="admin"
    ) is None
