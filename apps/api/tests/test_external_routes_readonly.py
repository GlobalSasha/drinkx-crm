"""Structural guard: the external surface exposes GET-only routes."""
from __future__ import annotations

from app.external.routers import router


def test_all_external_routes_are_get_only():
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        non_read = methods - {"GET", "HEAD", "OPTIONS"}
        assert not non_read, f"{route.path} exposes {non_read}"


def test_external_prefix():
    assert router.prefix == "/external/v1"


def test_expected_endpoints_present():
    paths = {r.path for r in router.routes}
    for p in [
        "/external/v1/leads",
        "/external/v1/leads/{lead_id}",
        "/external/v1/leads/{lead_id}/summary",
        "/external/v1/companies",
        "/external/v1/companies/{company_id}",
        "/external/v1/contacts",
        "/external/v1/pipelines",
        "/external/v1/pipelines/{pipeline_id}/summary",
        "/external/v1/meta",
    ]:
        assert p in paths, f"missing {p}"
