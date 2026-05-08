"""DrinkX Update Format v1.0 parser (PRD §6.14).

The format is YAML emitted by an external LLM (Claude / ChatGPT /
Perplexity) from the prompt the manager copies via /api/export/
bulk-update-prompt. Shape:

    format: drinkx-crm-update
    version: "1.0"
    updates:
      - action: update | create | skip
        match_by: inn | company_name | id
        company:
          name: ...
          inn: ...
        fields:
          ai_data: { ... }
          contacts: { add: [...], update_by_email: { ... } }
          tags: { add: [...], remove: [...] }
          stage: "Stage name"
          assigned_to: "user@email"

`is_bulk_update_yaml` is intentionally a fast pre-check (first ~1KB,
regex-only) so the upload handler can branch without parsing 250KB
files we already know are not bulk-update.
"""
from __future__ import annotations

import re
from typing import Any

import yaml


# Match "format: drinkx-crm-update" (with optional quotes around the value).
_FORMAT_LINE = re.compile(
    r"^\s*format\s*:\s*['\"]?drinkx-crm-update['\"]?",
    re.MULTILINE | re.IGNORECASE,
)
_UPDATES_KEY = re.compile(r"^\s*updates\s*:", re.MULTILINE)


VALID_ACTIONS = {"update", "create", "skip"}
VALID_MATCH_BYS = {"inn", "company_name", "id"}
_DETECT_HEAD_BYTES = 1024


def is_bulk_update_yaml(content: bytes) -> bool:
    """Cheap signature check on the first 1KB. We don't parse the file
    — just look for the magic header string + the `updates:` key.
    Returns False on decode errors so a malformed binary can't trick
    the auto-detect into routing through the diff engine."""
    if not content:
        return False
    head = content[:_DETECT_HEAD_BYTES]
    try:
        text = head.decode("utf-8", errors="ignore")
    except Exception:
        return False
    return bool(_FORMAT_LINE.search(text)) and bool(_UPDATES_KEY.search(text))


def parse_bulk_update(content: bytes) -> list[dict[str, Any]]:
    """Full parse. Returns list of update items with `action != 'skip'`
    and a valid `action` value. Items with malformed shape are silently
    dropped (we surface them as a count in the preview if needed —
    the LLM occasionally emits stub entries we'd rather ignore)."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    raw_updates = data.get("updates")
    if not isinstance(raw_updates, list):
        return []

    out: list[dict[str, Any]] = []
    for raw in raw_updates:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or "").strip().lower()
        if action not in VALID_ACTIONS:
            continue
        if action == "skip":
            continue
        # Defensive: silently drop entries with no company info — we
        # can't match or create without at least a name or inn.
        company = raw.get("company")
        if not isinstance(company, dict):
            continue
        if not (company.get("name") or company.get("inn")):
            continue
        # `fields` is allowed to be empty dict on `action=create` (the
        # AI just wants us to know about the company) but should still
        # be a dict for downstream typing.
        fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
        # Defaults: match_by guessed from what's available.
        match_by = str(raw.get("match_by") or "").strip().lower()
        if match_by not in VALID_MATCH_BYS:
            match_by = "inn" if company.get("inn") else "company_name"
        out.append({
            "action": action,
            "match_by": match_by,
            "company": company,
            "fields": fields,
        })
    return out


__all__ = [
    "VALID_ACTIONS",
    "VALID_MATCH_BYS",
    "is_bulk_update_yaml",
    "parse_bulk_update",
]
