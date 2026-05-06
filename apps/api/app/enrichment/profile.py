"""DrinkX business profile loader — read once, hand to synthesis prompt."""
from __future__ import annotations

import pathlib
from functools import lru_cache

import yaml
import structlog

log = structlog.get_logger()

_PROFILE_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "drinkx_profile.yaml"


@lru_cache(maxsize=1)
def load_profile() -> dict:
    """Load DrinkX profile YAML (cached for the process). Returns {} on failure."""
    try:
        return yaml.safe_load(_PROFILE_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        log.warning("profile.load_failed", error=str(e))
        return {}


def render_profile_for_prompt() -> str:
    """Format the profile as a compact text block for the synthesis system prompt."""
    p = load_profile()
    if not p:
        return ""
    company = p.get("company", {})
    objections = p.get("common_objections", [])
    signals = p.get("key_signals_to_extract", [])

    lines: list[str] = ["=== ПРОФИЛЬ DRINKX (контекст для оценки лида) ==="]
    if company.get("product"):
        lines.append(f"Продукт: {company['product'].strip()}")
    if company.get("positioning"):
        lines.append(f"Позиционирование: {company['positioning'].strip()}")
    if company.get("icp", {}).get("primary"):
        lines.append("ICP (приоритет): " + "; ".join(company["icp"]["primary"]))
    if company.get("icp", {}).get("secondary"):
        lines.append("ICP (вторично): " + "; ".join(company["icp"]["secondary"]))
    if company.get("fit_score_anchors"):
        anchors = company["fit_score_anchors"]
        lines.append("Fit-score шкала:")
        for k, v in anchors.items():
            lines.append(f"  {k} → {v}")
    if signals:
        lines.append("На что смотреть в источниках: " + "; ".join(signals))
    if objections:
        lines.append("Типовые возражения покупателей: " + "; ".join(objections))
    lines.append("=== / ПРОФИЛЬ ===")
    return "\n".join(lines)
