"""Pure helpers for computing storage object keys + sluggifying filenames.

Path layout: `{workspace_id}/{lead_id}/{activity_id}/{sluggified_filename}`.
Sluggification: lowercase, strip diacritics, ASCII transliteration for Cyrillic,
collapse non-[a-z0-9.] runs into a single hyphen, preserve the extension.
"""
from __future__ import annotations

import re
import unicodedata
import uuid

# Cyrillic → Latin (rough but stable; we only need a safe filesystem key)
_CYRILLIC_MAP = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


def _ascii_fold(s: str) -> str:
    # NFKD + drop combining marks, then translate Cyrillic
    s = s.lower()
    s = s.translate(_CYRILLIC_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def slug_filename(name: str) -> str:
    """Return a safe-for-storage filename. Preserves the extension."""
    raw = (name or "").strip()
    if not raw:
        return "file"

    # First pass: transliterate to ASCII and handle special chars
    # This lets us safely identify the extension even if the original had path separators
    raw_ascii = _ascii_fold(raw)

    # Remove path separators and dangerous patterns
    raw_ascii = raw_ascii.replace("/", " ").replace("\\", " ").replace("..", "")

    # Now split extension (look for the final dot in the cleaned ASCII version)
    if "." in raw_ascii:
        stem, _, ext = raw_ascii.rpartition(".")
        if not stem:  # ".hidden" → stem="", ext="hidden"
            stem, ext = ext, ""
    else:
        stem, ext = raw_ascii, ""

    # Collapse non-alphanumeric runs into single hyphens
    stem_safe = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    ext_safe = re.sub(r"[^a-z0-9]+", "", ext)

    if not stem_safe and not ext_safe:
        return "file"
    if ext_safe:
        return f"{stem_safe or 'file'}.{ext_safe}"
    return stem_safe or "file"


def build_object_key(
    *, workspace_id: uuid.UUID, lead_id: uuid.UUID, activity_id: uuid.UUID, filename: str
) -> str:
    """Storage key: `{ws}/{lead}/{activity}/{slug}`. Stable per Activity row."""
    return f"{workspace_id}/{lead_id}/{activity_id}/{slug_filename(filename)}"
