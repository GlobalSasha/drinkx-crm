"""Sprint 3.8 hotfix — per-manager pipeline scoping.

`GET /leads` is consumed by /pipeline and /today widgets. Both should
surface MY assigned leads, not every manager's. Before this fix the
`assigned_to` query param was optional with default None, and when
None was passed through to the repo no filter was applied → every
manager saw the whole workspace's assigned pile.

Fix: a small pure helper `_scope_assigned_to(explicit, user_id)`
defaults to `user_id` when explicit is None, and respects the
explicit value otherwise. Router uses it to construct the filters
dict.
"""
from __future__ import annotations

import sys
import uuid

import pytest


# Reuse the sqlalchemy stub helper from test_webforms.py so the routers
# module imports cleanly without dragging the declarative base.
from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

# `repositories.py` (transitively imported by routers.py) imports
# `defer` from `sqlalchemy.orm`; the shared stub doesn't include it.
# Same patch as in test_leads_source_enrichment.py.
_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    class _Callable:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
    _sa_orm.defer = _Callable()


def test_scope_assigned_to_falls_back_to_user_when_not_set():
    """No explicit ?assigned_to= and no text search → server scopes to
    the current user. That's how a new manager with zero assigned leads
    ends up with an empty pipeline instead of seeing the team's pile."""
    from app.leads.routers import _scope_assigned_to

    user_id = uuid.uuid4()
    assert _scope_assigned_to(None, user_id, None) == user_id
    # Empty string q is also "no search"
    assert _scope_assigned_to(None, user_id, "") == user_id


def test_scope_assigned_to_respects_explicit_value():
    """Admin who wants a cross-user view can still pass ?assigned_to=
    explicitly and override the default. Used by future admin / team
    views — current consumers don't pass it."""
    from app.leads.routers import _scope_assigned_to

    explicit = uuid.uuid4()
    user_id = uuid.uuid4()
    assert _scope_assigned_to(explicit, user_id, None) == explicit
    # Explicit value wins over text-search exemption too.
    assert _scope_assigned_to(explicit, user_id, "Coffee") == explicit


def test_scope_assigned_to_skips_default_when_text_search():
    """Text search → return None so the repo skips the assigned-to
    filter entirely. UnmatchedMessagesSection's lead-picker (assign a
    Telegram message to a colleague's lead) relies on this — without
    the exemption, a manager couldn't find another manager's lead by
    company name."""
    from app.leads.routers import _scope_assigned_to

    user_id = uuid.uuid4()
    assert _scope_assigned_to(None, user_id, "Coffee Roastery") is None
