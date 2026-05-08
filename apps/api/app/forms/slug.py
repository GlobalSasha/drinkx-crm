"""URL-safe slug generator with simple Cyrillic → Latin transliteration.

PRD example: «Форма для HoReCa» → "forma-dlya-horeca-a3x9kp" — the
6-char base36 suffix kicks the workspace-level collision rate down to
~36⁶ ≈ 2 billion possibilities, which is comfortable for any single
workspace's form catalog. The unique constraint on `web_forms.slug`
catches the rare collision; the service layer retries.

Stdlib only — no python-slugify dep.
"""
from __future__ import annotations

import re
import secrets

# ISO-9-ish RU → Latin map. Lowercase only; uppercase is handled by
# .lower() before lookup.
_TRANSLIT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # Ukrainian / Belarusian extras — cheap to support
    "і": "i", "ї": "yi", "є": "ye", "ў": "u",
}

_NON_SLUG_CHAR = re.compile(r"[^a-z0-9-]+")
_SUFFIX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_SUFFIX_LEN = 6


def _transliterate(text: str) -> str:
    out: list[str] = []
    for ch in text.lower():
        out.append(_TRANSLIT.get(ch, ch))
    return "".join(out)


def _random_suffix() -> str:
    """6-char base36 token. `secrets.choice` for cryptographic
    uniformity — collision probability stays at the theoretical
    36⁻⁶ regardless of how the caller is seeded."""
    return "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(_SUFFIX_LEN))


def generate_slug(name: str) -> str:
    """Convert any name to a URL-safe slug with a random suffix.

    Steps: transliterate Cyrillic → Latin, lowercase, collapse runs
    of non-`[a-z0-9-]` to single hyphens, strip leading/trailing
    hyphens, append a 6-char suffix.

    Returns at least `<suffix>` (10 chars) when the input has no
    transliterable characters at all (e.g. emoji-only) so the slug
    column never goes empty.
    """
    base = _transliterate(name or "")
    # Replace any whitespace/punct/hyphen run with a single hyphen
    base = base.replace("_", "-")
    base = _NON_SLUG_CHAR.sub("-", base)
    base = re.sub(r"-+", "-", base).strip("-")
    suffix = _random_suffix()
    if not base:
        return suffix
    # Cap base length so the full slug + suffix + dash fits comfortably
    # under web_forms.slug VARCHAR(100). Headroom for future
    # workspace-prefix variants.
    base = base[:80]
    return f"{base}-{suffix}"


__all__ = ["generate_slug"]
