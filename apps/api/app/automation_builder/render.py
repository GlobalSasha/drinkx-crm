"""Template variable substitution — Sprint 2.5 G1.

`render_template_text(text, lead)` substitutes `{{lead.<field>}}`
placeholders against allowlisted Lead fields. Unknown fields render
as `[unknown:field]` and emit a worker-log warning — better than
silently leaving the literal `{{lead.foo}}` in the outbound message,
and easier to spot in audit logs than a raw KeyError.

Risk note from `04_NEXT_SPRINT.md`: keep the allowlist explicit so
removing a Lead column doesn't silently break already-deployed
templates.
"""
from __future__ import annotations

import re

import structlog

from app.leads.models import Lead

log = structlog.get_logger()


# Same allowlist as condition.ALLOWED_FIELDS — plus rendering-only
# fields the user might want in a message body. Keep these two lists
# narrow and explicit.
RENDER_FIELDS = (
    "company_name",
    "city",
    "email",
    "phone",
    "website",
    "segment",
    "deal_type",
    "priority",
    "score",
    "source",
    "next_step",
    "blocker",
)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*lead\.([a-z_][a-z0-9_]*)\s*\}\}")


def render_template_text(text: str, lead: Lead) -> str:
    """Substitute `{{lead.field}}` against the lead. Return the new
    string. Defensive — never raises; unknown fields → `[unknown:foo]`."""
    def _sub(m: re.Match[str]) -> str:
        field = m.group(1)
        if field not in RENDER_FIELDS:
            log.warning("automation.render.unknown_field", field=field)
            return f"[unknown:{field}]"
        val = getattr(lead, field, None)
        if val is None:
            return ""
        return str(val)

    return _PLACEHOLDER_RE.sub(_sub, text)
