"""Batch dedup (#6): group extracted cards that refer to the same company.

Pure function — no DB. Grouping key is companies.utils.normalize_company_name.
Cards in a group whose scalar company fields diverge are flagged as a #6
conflict for the admin; otherwise the group is merged silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.base_update.schemas import ExtractedCard
from app.companies.utils import normalize_company_name

_MERGE_FIELDS = ("segment", "priority", "website", "inn", "city", "phone", "email")


@dataclass
class DedupGroup:
    normalized_name: str
    cards: list[ExtractedCard] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    conflict: bool = False
    conflict_field: str | None = None

    @property
    def primary(self) -> ExtractedCard:
        """The card with the most non-empty scalar fields wins as the merge base."""
        if not self.cards:
            raise ValueError("DedupGroup has no cards")
        return max(self.cards, key=_field_count)


def _field_count(card: ExtractedCard) -> int:
    return sum(1 for f in _MERGE_FIELDS if getattr(card.company, f))


def dedup_batch(items: list[tuple[ExtractedCard, list[str]]]) -> list[DedupGroup]:
    """Group cards by normalized company name. Returns groups in first-seen order."""
    by_key: dict[str, DedupGroup] = {}
    for card, files in items:
        key = normalize_company_name(card.company.name or "")
        grp = by_key.get(key)
        if grp is None:
            grp = DedupGroup(normalized_name=key)
            by_key[key] = grp
        grp.cards.append(card)
        for f in files:
            if f not in grp.source_files:
                grp.source_files.append(f)
    for grp in by_key.values():
        if len(grp.cards) > 1:
            _flag_divergence(grp)
    return list(by_key.values())


def _flag_divergence(grp: DedupGroup) -> None:
    """If any merge-field has >1 distinct non-empty value across the group, flag it."""
    for f in _MERGE_FIELDS:
        seen = {str(getattr(c.company, f)) for c in grp.cards if getattr(c.company, f)}
        if len(seen) > 1:
            grp.conflict = True
            grp.conflict_field = f
            return
