#!/usr/bin/env python3
"""Convert v0.6 foodmarkets-candidates .md files into a window.REAL_DATA JS file
that the existing import_prototype_data.py can consume.

YAML frontmatter shape (from drinkx-client-map-v0.6-foodmarkets-audit/07_foodmarkets_candidates/*.md):
---
type: candidate_client
project: DrinkX
client_name: "..."
foodmarkets_id: "..."
foodmarkets_url: "https://foodmarkets.ru/..."
verification_status: needs_verification
priority: A
drinkx_score: 60
inferred_segment: "coffee_or_ready_food"
tags: [drinkx, candidate-client, foodmarkets-v06, needs-verification]
---
# Title

Description body...
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-ish frontmatter at the top of a markdown file.

    Tolerant: handles only the simple key:value subset we see in foodmarkets MDs.
    Returns (meta_dict, body_string).
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip("\n")
    body = text[end + 4 :].lstrip("\n")

    meta: dict[str, Any] = {}
    for line in fm.splitlines():
        line = line.rstrip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        # strip surrounding quotes
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        # list literal
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1]
            items = [s.strip().strip("'\"") for s in inner.split(",") if s.strip()]
            meta[k] = items
            continue
        # int
        if re.fullmatch(r"-?\d+", v):
            meta[k] = int(v)
            continue
        meta[k] = v
    return meta, body


def _convert(md_path: pathlib.Path) -> dict[str, Any] | None:
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = _parse_frontmatter(text)
    name = (meta.get("client_name") or "").strip()
    if not name:
        return None

    raw_priority = (meta.get("priority") or "").strip()
    priority = raw_priority if raw_priority in ("A", "B", "C", "D") else None

    fm_url = meta.get("foodmarkets_url") or ""
    fm_id = meta.get("foodmarkets_id") or md_path.stem

    # Strip the "## Описание из Foodmarkets" heading + return the immediate paragraph
    overview_match = re.search(
        r"^## Описание из Foodmarkets\s*\n+(.+?)(?=\n##|\Z)",
        body,
        re.S | re.M,
    )
    overview = overview_match.group(1).strip() if overview_match else body.strip()
    overview = re.sub(r"\s+", " ", overview)[:2000]

    # Pull "Сигналы для DrinkX" bullet list as sales_triggers
    signals_match = re.search(
        r"^## Сигналы для DrinkX\s*\n+(.*?)(?=\n##|\Z)",
        body,
        re.S | re.M,
    )
    triggers: list[str] = []
    if signals_match:
        for line in signals_match.group(1).splitlines():
            line = line.strip()
            if line.startswith("- ") and len(line) > 2:
                triggers.append(line[2:].strip())

    return {
        "id": str(fm_id),
        "company_name": name,
        # All foodmarkets candidates are food retail by their nature
        "segment": "food_retail",
        "segment_label": "Продуктовый ритейл",
        "tier": None,
        "priority": priority,
        "website": fm_url or None,  # foodmarkets listing as a placeholder source
        "company_overview": overview,
        "network_scale": None,
        "geography": None,
        "formats": None,
        "coffee_signals": meta.get("inferred_segment") or None,
        "sales_triggers": triggers,
        "entry_route": None,
        "research_gaps": "Verification needed (foodmarkets v0.6 candidate)",
        "confidence": "low",
        "decision_makers": [],
        "people_to_verify": [],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--source",
        default="/Users/aleksandrhvastunov/Desktop/crm-prototype/drinkx-client-map-v0.6-foodmarkets-audit/07_foodmarkets_candidates",
    )
    p.add_argument(
        "--out",
        default="/Users/aleksandrhvastunov/Desktop/crm-prototype/data_foodmarkets_v0.6.js",
    )
    args = p.parse_args()

    src = pathlib.Path(args.source).expanduser().resolve()
    if not src.is_dir():
        print(f"[ERROR] source not a directory: {src}", file=sys.stderr)
        sys.exit(1)

    leads: list[dict[str, Any]] = []
    for md in sorted(src.glob("*.md")):
        row = _convert(md)
        if row is None:
            continue
        leads.append(row)

    out_path = pathlib.Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"leads": leads}
    out_path.write_text(
        "// Auto-generated from drinkx-client-map-v0.6-foodmarkets-audit/07_foodmarkets_candidates\n"
        f"// {len(leads)} candidate leads\n\n"
        "window.REAL_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=1)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(leads)} foodmarkets candidates → {out_path}")


if __name__ == "__main__":
    main()
