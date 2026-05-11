"""Migrate prototype-shape `ai_data` into ResearchOutput shape.

Reads `crm-prototype/data.js` + `data_foodmarkets_v0.6.js`, matches each
prototype lead to a row in `leads` by normalised `company_name`, and
re-shapes the JSON payload according to the mapping in the sprint spec.

**Skip rule:** if `lead.ai_data` already contains the key
`company_profile`, the row is in the new schema and we leave it alone.

**Default mode:** `--dry-run`. Writes nothing. Prints a summary
(updated / skipped / missing / contacts to add). Run with `--apply` to
actually UPDATE the rows.

Usage:
    DATABASE_URL=postgresql+asyncpg://drinkx:...@host:5432/drinkx_crm \\
        python3 scripts/migrate_ai_data_from_base.py [--apply]

    # On the prod server:
    ssh drinkx-crm 'cd /opt/drinkx-crm/apps/api && \\
        DATABASE_URL=postgresql+asyncpg://drinkx:$POSTGRES_PASSWORD@postgres:5432/drinkx_crm \\
        uv run python /opt/drinkx-crm/scripts/migrate_ai_data_from_base.py'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOTYPE_ROOT = REPO_ROOT.parent / "crm-prototype"
DATA_FILES = [
    PROTOTYPE_ROOT / "data.js",
    PROTOTYPE_ROOT / "data_foodmarkets_v0.6.js",
]


def _parse_data_js(path: Path) -> list[dict[str, Any]]:
    """Strip the `window.REAL_DATA = ` prefix and trailing `;` to get JSON."""
    raw = path.read_text(encoding="utf-8")
    start = raw.index("{")
    end = raw.rindex("}")
    payload = json.loads(raw[start : end + 1])
    return payload.get("leads", [])


_NORMALISE_RX = re.compile(r"[^\w\s]", re.UNICODE)


def _normalise(name: str) -> str:
    return _NORMALISE_RX.sub("", (name or "")).strip().casefold()


def _extract_label(md_link: str) -> str:
    """`[Label](https://url)` → `Label`. Falls back to the URL itself."""
    m = re.match(r"\s*\[(.+?)\]\((.+?)\)\s*", md_link or "")
    if m:
        return m.group(1).strip()
    return (md_link or "").strip()


def _coerce_list(v: Any) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    parts = re.split(r"[;\n]", str(v))
    return [p.strip() for p in parts if p.strip()]


def _build_new_ai_data(proto: dict[str, Any]) -> dict[str, Any]:
    """Map prototype-shape → new ResearchOutput-extended shape."""
    scale_parts = [
        proto.get("network_scale", ""),
        proto.get("geography", ""),
        proto.get("formats", ""),
    ]
    scale_signals = " · ".join(p for p in (s.strip() if isinstance(s, str) else "" for s in scale_parts) if p)

    coffee = _coerce_list(proto.get("coffee_signals"))
    triggers = _coerce_list(proto.get("sales_triggers"))
    growth_signals = coffee + triggers

    risk_signals = _coerce_list(proto.get("risk_signals"))

    next_steps: list[str] = []
    entry_route = proto.get("entry_route")
    if entry_route:
        next_steps.append(str(entry_route).strip())

    sources_used = [_extract_label(s) for s in (proto.get("source_links_md") or [])]

    hint_lines: list[str] = []
    for person in (proto.get("decision_makers") or []) + (proto.get("people_to_verify") or []):
        name = (person.get("name") or "").strip()
        title = (person.get("title") or "").strip()
        conf = (person.get("confidence") or "").strip().lower() or "low"
        if not name:
            continue
        hint_lines.append(
            {
                "name": name,
                "title": title,
                "role": (person.get("role") or "").strip(),
                "confidence": conf if conf in ("high", "medium", "low") else "low",
                "source": _extract_label(person.get("source") or ""),
            }
        )

    proto_fit = proto.get("fit_score")
    try:
        drinkx_fit = int(round(float(proto_fit))) if proto_fit is not None else 5
    except (TypeError, ValueError):
        drinkx_fit = 5
    drinkx_fit = max(0, min(10, drinkx_fit))

    return {
        "company_profile": (proto.get("company_overview") or "").strip(),
        "network_scale": (proto.get("network_scale") or "").strip(),
        "geography": (proto.get("geography") or "").strip(),
        "formats": _coerce_list(proto.get("formats")) if isinstance(proto.get("formats"), list) else (proto.get("formats") or ""),
        "coffee_signals": coffee,
        "growth_signals": growth_signals,
        "risk_signals": risk_signals,
        "decision_maker_hints": hint_lines,
        "contacts_found": [],
        "fit_score": float(drinkx_fit),
        "next_steps": next_steps,
        "urgency": "",
        "sources_used": sources_used,
        "notes": "",
        "score_rationale": "",
        # New extended fields (Sprint Lead Card Redesign)
        "scale_signals": scale_signals,
        "drinkx_fit_score": drinkx_fit,
        "research_gaps": (proto.get("research_gaps") or "").strip(),
    }


def _new_contacts_for_lead(proto: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Contact row dicts to be inserted for this lead.

    Skips entries where the `name` field is clearly not a person — the
    prototype's `people_to_verify` was used by researchers as a free-form
    TODO list, so some entries contain entire sentences instead of a
    name. `contacts.name` is varchar(120); we conservatively drop
    anything > 120 chars or > 6 whitespace-separated tokens.
    """
    def _looks_like_name(s: str) -> bool:
        s = (s or "").strip()
        return 0 < len(s) <= 120 and len(s.split()) <= 6

    out: list[dict[str, Any]] = []
    for person in proto.get("decision_makers") or []:
        if not _looks_like_name(person.get("name") or ""):
            continue
        conf = (person.get("confidence") or "high").strip().lower()
        out.append(
            {
                "name": person["name"].strip(),
                "title": (person.get("title") or "").strip()[:120] or None,
                "role_type": None,  # prototype's "role" is free-form Russian text
                "source": "prototype_migration",
                "confidence": conf if conf in ("high", "medium", "low") else "high",
                "verified_status": "verified",
                "notes": (person.get("source") or "").strip()[:1000] or None,
            }
        )
    for person in proto.get("people_to_verify") or []:
        if not _looks_like_name(person.get("name") or ""):
            continue
        out.append(
            {
                "name": person["name"].strip(),
                "title": (person.get("title") or "").strip()[:120] or None,
                "role_type": None,
                "source": "prototype_migration",
                "confidence": "low",
                "verified_status": "to_verify",
                "notes": (person.get("source") or "").strip()[:1000] or None,
            }
        )
    return out


async def main(apply_changes: bool) -> int:
    import asyncpg  # lazy — helpers above are pure and unit-testable

    proto_leads: list[dict[str, Any]] = []
    for path in DATA_FILES:
        if not path.exists():
            print(f"⚠ missing {path}", file=sys.stderr)
            continue
        proto_leads.extend(_parse_data_js(path))
    print(f"loaded {len(proto_leads)} prototype leads from {len(DATA_FILES)} file(s)")

    db_url = os.environ.get("DATABASE_URL", "")
    # asyncpg uses plain postgresql://, not the SQLAlchemy +asyncpg dialect.
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    if not db_url:
        print("✗ DATABASE_URL not set", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch("SELECT id, company_name, ai_data FROM leads")
        db_by_norm: dict[str, dict[str, Any]] = {}
        for r in rows:
            key = _normalise(r["company_name"])
            if key:
                db_by_norm.setdefault(key, dict(r))
        print(f"loaded {len(rows)} DB leads ({len(db_by_norm)} unique normalised names)")

        existing_contacts = await conn.fetch(
            "SELECT lead_id, lower(name) AS lname FROM contacts"
        )
        existing_set: set[tuple[str, str]] = {
            (str(c["lead_id"]), c["lname"]) for c in existing_contacts
        }

        updated = 0
        skipped_new_schema = 0
        missing_in_db = 0
        contacts_to_add = 0
        contacts_skipped_exist = 0

        for proto in proto_leads:
            key = _normalise(proto.get("company_name") or "")
            db_row = db_by_norm.get(key)
            if db_row is None:
                missing_in_db += 1
                continue

            ai = db_row["ai_data"]
            if isinstance(ai, str):
                try:
                    ai_obj = json.loads(ai)
                except json.JSONDecodeError:
                    ai_obj = {}
            else:
                ai_obj = ai or {}
            in_new_schema = bool(ai_obj.get("company_profile"))
            if in_new_schema:
                skipped_new_schema += 1
            else:
                new_ai_data = _build_new_ai_data(proto)
                if apply_changes:
                    await conn.execute(
                        "UPDATE leads SET ai_data = $1::jsonb, updated_at = now() WHERE id = $2",
                        json.dumps(new_ai_data, ensure_ascii=False),
                        db_row["id"],
                    )
                updated += 1

            for c in _new_contacts_for_lead(proto):
                if (str(db_row["id"]), c["name"].lower()) in existing_set:
                    contacts_skipped_exist += 1
                    continue
                contacts_to_add += 1
                if apply_changes:
                    await conn.execute(
                        """
                        INSERT INTO contacts
                          (id, created_at, updated_at, lead_id, name, title, role_type,
                           source, confidence, verified_status, notes)
                        VALUES
                          (gen_random_uuid(), now(), now(), $1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        db_row["id"],
                        c["name"],
                        c["title"],
                        c["role_type"],
                        c["source"],
                        c["confidence"],
                        c["verified_status"],
                        c["notes"],
                    )
                    existing_set.add((str(db_row["id"]), c["name"].lower()))

        print()
        print("=" * 60)
        print(f"  Mode: {'APPLY' if apply_changes else 'DRY-RUN'}")
        print("=" * 60)
        print(f"  prototype leads scanned : {len(proto_leads)}")
        print(f"  ai_data rewritten       : {updated}")
        print(f"  skipped (new schema)    : {skipped_new_schema}")
        print(f"  prototype not in DB     : {missing_in_db}")
        print(f"  contacts to insert      : {contacts_to_add}")
        print(f"  contacts already there  : {contacts_skipped_exist}")
        print("=" * 60)
        if not apply_changes:
            print("dry-run only — no rows changed. Re-run with --apply to write.")
        else:
            print("APPLY complete. Rows committed.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Default is dry-run.",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(main(apply_changes=args.apply)))
