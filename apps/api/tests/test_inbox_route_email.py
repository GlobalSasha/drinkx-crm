"""Sprint 3.6 hotfix — bulk-mail pre-filter in `route_email`.

Covers the four new bulk-mail signals so AI doesn't burn tokens on
PlayStation Plus billing reminders, Substack newsletters, Google
Workspace notifications and webinar invites.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# Reuse the sqlalchemy stub helper from test_webforms.py so the import
# of `processor` doesn't pull the declarative base.
from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


# ---------------------------------------------------------------------------
# RFC headers — `List-Unsubscribe`, `Precedence`, `Auto-Submitted`
# ---------------------------------------------------------------------------


def test_list_unsubscribe_header_routes_to_ignore():
    """RFC 2369: any sender that ships `List-Unsubscribe` is by
    definition a bulk mailer and should never reach AI."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="email@email.playstation.com",
        subject="PlayStation Plus: Upcoming payment",
        body_preview="Your subscription will renew on...",
        has_known_company=False,
        has_known_contact=False,
        headers={"list-unsubscribe": "<mailto:unsubscribe@playstation.com>"},
    )

    assert decision.route == "ignore"
    assert decision.reason == "list_unsubscribe_header"


def test_list_unsubscribe_post_header_routes_to_ignore():
    """RFC 8058: one-click unsubscribe variant should also trigger ignore."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="news@substack.com",
        subject="Is Uber Eats Eying A Delivery Hero Acquisition?",
        body_preview="View this post on the web at...",
        has_known_company=False,
        has_known_contact=False,
        headers={"list-unsubscribe-post": "List-Unsubscribe=One-Click"},
    )

    assert decision.route == "ignore"
    assert decision.reason == "list_unsubscribe_header"


def test_precedence_bulk_header_routes_to_ignore():
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="news@example.com",
        subject="Weekly digest",
        body_preview="",
        has_known_company=False,
        has_known_contact=False,
        headers={"precedence": "bulk"},
    )

    assert decision.route == "ignore"
    assert decision.reason == "precedence_bulk"


def test_auto_submitted_header_routes_to_ignore():
    """RFC 3834: `Auto-Submitted: auto-generated` (or anything other
    than `no`) is an automated bounce / vacation responder."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="bounce@example.com",
        subject="Delivery Status Notification (Failure)",
        body_preview="Your message could not be delivered.",
        has_known_company=False,
        has_known_contact=False,
        headers={"auto-submitted": "auto-generated"},
    )

    assert decision.route == "ignore"
    assert decision.reason == "auto_submitted"


def test_auto_submitted_no_does_not_ignore():
    """Some MTAs put `Auto-Submitted: no` to be explicit. That must
    NOT trigger the ignore branch."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="alice@coffee-shop.ru",
        subject="Запрос на демонстрацию",
        body_preview="Здравствуйте, интересует кофе-станция...",
        has_known_company=False,
        has_known_contact=False,
        headers={"auto-submitted": "no"},
    )

    assert decision.route == "inbox"


# ---------------------------------------------------------------------------
# Substring noreply match — `workspace-noreply@google.com` and similar
# ---------------------------------------------------------------------------


def test_workspace_noreply_caught_by_substring():
    """`workspace-noreply@google.com` doesn't start with `noreply@` but
    contains `noreply` in the local-part. Substring branch catches it."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="workspace-noreply@google.com",
        subject="Напоминание о связанных сервисах Google",
        body_preview="Google Workspace logo Настройки можно изменить...",
        has_known_company=False,
        has_known_contact=False,
    )

    assert decision.route == "ignore"
    assert decision.reason == "noreply_substring"


def test_email_noreply_caught_by_substring():
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="email-noreply@playstation.com",
        subject="Login alert",
        body_preview="",
        has_known_company=False,
        has_known_contact=False,
    )

    assert decision.route == "ignore"
    assert decision.reason == "noreply_substring"


def test_real_corporate_sender_passes_through():
    """Genuine person at unknown corporate domain should still reach the
    inbox (not blocked by noreply-substring false positive)."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="ivan.petrov@coffee-roastery.ru",
        subject="Запрос коммерческого предложения",
        body_preview="Здравствуйте, рассматриваем DrinkX для наших точек.",
        has_known_company=False,
        has_known_contact=False,
    )

    assert decision.route == "inbox"
    assert decision.reason == "unknown_corporate_domain"


# ---------------------------------------------------------------------------
# Header priority — bulk headers beat the known-contact attach path
# ---------------------------------------------------------------------------


def test_list_unsubscribe_beats_known_contact():
    """A known contact who sends an unsubscribe-enabled bulk email
    (e.g. they signed us up to their newsletter from a tracked address)
    should NOT auto-attach to their lead. List-Unsubscribe always wins."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="contact@known-customer.ru",
        subject="Newsletter — Q3 update",
        body_preview="Read the latest news from our team...",
        has_known_company=False,
        has_known_contact=True,
        headers={"list-unsubscribe": "<mailto:u@known-customer.ru>"},
    )

    assert decision.route == "ignore"
    assert decision.reason == "list_unsubscribe_header"


# ---------------------------------------------------------------------------
# Backward compat — old call sites that don't pass `headers` still work
# ---------------------------------------------------------------------------


def test_headers_kwarg_optional():
    """Existing tests / callers that don't pass `headers` keep working."""
    from app.inbox import processor as p

    decision = p.route_email(
        from_email="noreply@example.com",
        subject="X",
        body_preview="Y",
        has_known_company=False,
        has_known_contact=False,
    )

    assert decision.route == "ignore"
    assert decision.reason == "noreply_sender"


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
