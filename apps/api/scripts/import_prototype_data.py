"""One-shot loader for the 131 prototype leads (Sprint 1.2 Task 8).

Source: ~/Desktop/crm-prototype/data.js (window.REAL_DATA dict)
Target: Postgres via app.db AsyncSessionLocal

Idempotent: skips leads where company_name already exists in workspace.
Sets assignment_status='pool' so managers can claim via Sprint generator.

Usage (on production server):
  cd /opt/drinkx-crm/apps/api
  uv run python scripts/import_prototype_data.py
  # or with options:
  uv run python scripts/import_prototype_data.py --source /path/to/data.js --limit 10 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
from typing import Any

from sqlalchemy import select

# Ensure the app package is importable when running from apps/api/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.auth.models import Workspace
from app.contacts.models import Contact, ContactRoleType
from app.db import get_session_factory
from app.leads.models import Lead
from app.pipelines.models import Pipeline, Stage

# Side-effect imports so the SQLAlchemy mapper registry can resolve string-based
# relationships from Lead -> Activity / Followup. Without these the very first
# query against any model trips: "expression 'Activity' failed to locate a name".
from app.activity import models as _activity_models  # noqa: F401
from app.followups import models as _followups_models  # noqa: F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRIORITY_SCORE: dict[str, int] = {"A": 85, "B": 65, "C": 45, "D": 25}
VALID_PRIORITIES = set(PRIORITY_SCORE.keys())

# Role heuristics (case-insensitive substring match)
_CHAMPION_HINTS = ("ceo", "основатель", "владелец")
_ECONOMIC_BUYER_HINTS = ("финанс", "cfo")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_source(path: pathlib.Path) -> list[dict[str, Any]]:
    """Read data.js, strip the JS wrapper, return the list of lead dicts."""
    src = path.read_text(encoding="utf-8")
    m = re.search(r"window\.REAL_DATA\s*=\s*(\{.*\});?\s*$", src, re.S)
    if not m:
        raise ValueError(f"Could not find window.REAL_DATA assignment in {path}")
    data = json.loads(m.group(1))
    return data["leads"]


def _derive_role_type(role: str | None) -> str | None:
    """Return ContactRoleType value from a free-text role string, or None."""
    if not role:
        return None
    role_lower = role.lower()
    if any(hint in role_lower for hint in _CHAMPION_HINTS):
        return ContactRoleType.champion.value
    if any(hint in role_lower for hint in _ECONOMIC_BUYER_HINTS):
        return ContactRoleType.economic_buyer.value
    return None


def _normalize_confidence(raw: str | None) -> str:
    """Coerce a free-form confidence string ('Medium (2022, current?)', 'High')
    into one of {"high", "medium", "low"} so it fits Contact.confidence VARCHAR(20)."""
    if not raw:
        return "medium"
    head = raw.strip().split()[0].lower() if raw.strip() else ""
    if head.startswith("high"):
        return "high"
    if head.startswith("low"):
        return "low"
    return "medium"


def _build_ai_data(lead: dict[str, Any]) -> dict[str, Any]:
    """Roll up research fields into the ai_data JSON blob."""
    return {
        "company_overview": lead.get("company_overview"),
        "network_scale": lead.get("network_scale"),
        "geography": lead.get("geography"),
        "formats": lead.get("formats"),
        "coffee_signals": lead.get("coffee_signals"),
        "sales_triggers": lead.get("sales_triggers"),
        "entry_route": lead.get("entry_route"),
        "research_gaps": lead.get("research_gaps"),
        "confidence": lead.get("confidence"),
        "source_id": lead.get("id"),
    }


def _build_dry_run_row(lead: dict[str, Any]) -> dict[str, Any]:
    """Return the would-be Lead DB row as a plain dict (for --dry-run output)."""
    raw_priority = lead.get("priority")
    priority = raw_priority if raw_priority in VALID_PRIORITIES else None
    score = PRIORITY_SCORE.get(priority or "", 0)
    segment_label = lead.get("segment_label")
    return {
        "company_name": lead.get("company_name"),
        "segment": lead.get("segment"),
        "priority": priority,
        "score": score,
        "fit_score": None,
        "website": lead.get("website"),
        "assignment_status": "pool",
        "assigned_to": None,
        "assigned_at": None,
        "ai_data": _build_ai_data(lead),
        "tags_json": [segment_label] if segment_label else [],
        "pipeline_id": "<default-pipeline-uuid>",
        "stage_id": "<position-0-stage-uuid>",
        "contacts_from_decision_makers": [
            {
                "name": c.get("name"),
                "title": c.get("title"),
                "role_type": _derive_role_type(c.get("role")),
                "source": "research",
                "confidence": _normalize_confidence(c.get("confidence")),
                "verified_status": "verified",
                "notes": c.get("source"),
            }
            for c in lead.get("decision_makers", [])
        ],
        "contacts_from_people_to_verify": [
            {
                "name": c.get("name"),
                "title": c.get("title"),
                "role_type": _derive_role_type(c.get("role")),
                "source": "research",
                "confidence": "low",
                "verified_status": "to_verify",
                "notes": c.get("source"),
            }
            for c in lead.get("people_to_verify", [])
        ],
    }


# ---------------------------------------------------------------------------
# Core import logic
# ---------------------------------------------------------------------------


async def main(args: argparse.Namespace) -> None:
    source_path = pathlib.Path(args.source).expanduser().resolve()
    if not source_path.exists():
        print(f"[ERROR] Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    all_leads = _parse_source(source_path)
    total = len(all_leads)
    print(f"Parsed {total} leads from {source_path}")

    if args.limit:
        all_leads = all_leads[: args.limit]
        print(f"Limiting to first {args.limit} leads (--limit flag)")

    # ---- dry-run mode -------------------------------------------------------
    if args.dry_run:
        print("\n--- DRY-RUN: first 3 would-be DB rows ---\n")
        for i, lead in enumerate(all_leads[:3]):
            row = _build_dry_run_row(lead)
            print(f"[{i + 1}] {row['company_name']}")
            print(json.dumps(row, ensure_ascii=False, indent=2))
            print()
        print("(dry-run complete — nothing written to DB)")
        return

    # ---- real import --------------------------------------------------------
    factory = get_session_factory()

    imported = 0
    skipped = 0
    contacts_created = 0
    failed_company: str | None = None

    async with factory() as session:
        async with session.begin():
            # 1. Find first workspace
            ws_result = await session.execute(select(Workspace).limit(1))
            workspace = ws_result.scalar_one_or_none()
            if workspace is None:
                print("[ERROR] No workspace found in DB. Run the app first so a workspace is bootstrapped.", file=sys.stderr)
                sys.exit(1)
            workspace_id = workspace.id
            print(f"Using workspace: {workspace.name!r} ({workspace_id})")

            # 2. Find default pipeline (is_default=True, fallback to first)
            pipeline_result = await session.execute(
                select(Pipeline)
                .where(Pipeline.workspace_id == workspace_id)
                .order_by(Pipeline.is_default.desc(), Pipeline.position.asc())
                .limit(1)
            )
            pipeline = pipeline_result.scalar_one_or_none()
            if pipeline is None:
                print("[ERROR] No pipeline found for workspace.", file=sys.stderr)
                sys.exit(1)
            pipeline_id = pipeline.id
            print(f"Using pipeline: {pipeline.name!r} ({pipeline_id})")

            # 3. Find position-0 stage
            stage_result = await session.execute(
                select(Stage)
                .where(Stage.pipeline_id == pipeline_id)
                .order_by(Stage.position.asc())
                .limit(1)
            )
            stage = stage_result.scalar_one_or_none()
            if stage is None:
                print("[ERROR] No stages found for pipeline.", file=sys.stderr)
                sys.exit(1)
            stage_id = stage.id
            print(f"Using entry stage: {stage.name!r} ({stage_id})")
            print()

            # 4. Load existing company names to detect duplicates efficiently
            existing_result = await session.execute(
                select(Lead.company_name).where(Lead.workspace_id == workspace_id)
            )
            existing_names: set[str] = {row[0] for row in existing_result.all()}

            # 5. Iterate leads
            for idx, lead in enumerate(all_leads, start=1):
                company_name = lead.get("company_name", "")
                failed_company = company_name  # track for error reporting

                n_total = len(all_leads)

                if company_name in existing_names:
                    print(f"[{idx}/{n_total}] - Skipped: {company_name} (already exists)")
                    skipped += 1
                    continue

                # Derive fields
                raw_priority = lead.get("priority")
                priority = raw_priority if raw_priority in VALID_PRIORITIES else None
                score = PRIORITY_SCORE.get(priority or "", 0)
                segment_label = lead.get("segment_label")

                new_lead = Lead(
                    workspace_id=workspace_id,
                    pipeline_id=pipeline_id,
                    stage_id=stage_id,
                    company_name=company_name,
                    segment=lead.get("segment"),
                    website=lead.get("website"),
                    priority=priority,
                    score=score,
                    fit_score=None,
                    assignment_status="pool",
                    assigned_to=None,
                    assigned_at=None,
                    ai_data=_build_ai_data(lead),
                    tags_json=[segment_label] if segment_label else [],
                )
                session.add(new_lead)
                # Flush so new_lead.id is populated before creating contacts
                await session.flush()

                # Contacts: decision_makers → verified
                lead_contacts = 0
                for c in lead.get("decision_makers", []):
                    name = c.get("name", "").strip()
                    if not name:
                        continue
                    contact = Contact(
                        lead_id=new_lead.id,
                        name=name[:120],
                        title=(c.get("title") or "")[:120] or None,
                        role_type=_derive_role_type(c.get("role")),
                        source="research",
                        confidence=_normalize_confidence(c.get("confidence")),
                        verified_status="verified",
                        notes=c.get("source"),
                    )
                    session.add(contact)
                    lead_contacts += 1

                # Contacts: people_to_verify → to_verify
                for c in lead.get("people_to_verify", []):
                    name = c.get("name", "").strip()
                    if not name:
                        continue
                    contact = Contact(
                        lead_id=new_lead.id,
                        name=name[:120],
                        title=(c.get("title") or "")[:120] or None,
                        role_type=_derive_role_type(c.get("role")),
                        source="research",
                        confidence="low",
                        verified_status="to_verify",
                        notes=c.get("source"),
                    )
                    session.add(contact)
                    lead_contacts += 1

                print(f"[{idx}/{n_total}] ✓ Created: {company_name} ({lead_contacts} contacts)")
                imported += 1
                contacts_created += lead_contacts
                existing_names.add(company_name)  # prevent dupes within this run

        # Transaction committed here
        failed_company = None  # clear — we're past the commit

    print()
    print(f"Imported {imported} leads, {skipped} skipped, {contacts_created} contacts created")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-shot loader for 131 prototype leads into DrinkX CRM DB."
    )
    parser.add_argument(
        "--source",
        default="~/Desktop/crm-prototype/data.js",
        help="Path to data.js file (default: ~/Desktop/crm-prototype/data.js)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be imported without writing to DB",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only import the first N leads (0 = all)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
