"""Per-user UI preferences — canonical defaults + validation.

Keys live in `users.ui_prefs_json` (JSONB). The column starts empty;
the resolver below merges over `DEFAULTS` so the API always returns
a fully-shaped object and the frontend never has to guess.

Adding a new key: extend `DEFAULTS` + `ALLOWED_VALUES` and the
PATCH endpoint accepts it automatically. Removing a key is a
data-migration concern — drop it from `ALLOWED_VALUES` here AND
clean it from existing rows, otherwise the resolver silently keeps
serving the old value.
"""
from __future__ import annotations

from typing import Any


# Canonical defaults — the shape the API guarantees to return when
# the user has not customised anything.
DEFAULTS: dict[str, Any] = {
    "sidebar_color":    "white",        # white | cream | beige | graphite | coffee
    "background_color": "cream",        # cream | white
    "density":          "comfortable",  # comfortable | compact
    "font_size":        "md",           # sm | md | lg
}


# Whitelist of accepted values per key. PATCH rejects anything else.
ALLOWED_VALUES: dict[str, set[str]] = {
    "sidebar_color":    {"white", "cream", "beige", "graphite", "coffee"},
    "background_color": {"cream", "white"},
    "density":          {"comfortable", "compact"},
    "font_size":        {"sm", "md", "lg"},
}


def resolve(stored: dict | None) -> dict[str, Any]:
    """Merge stored prefs over defaults so every key is always present."""
    if not stored:
        return dict(DEFAULTS)
    out = dict(DEFAULTS)
    for k, v in stored.items():
        if k in ALLOWED_VALUES and v in ALLOWED_VALUES[k]:
            out[k] = v
    return out


def validate_patch(patch: dict) -> dict[str, Any]:
    """Validate a partial update. Raises ValueError on unknown keys or
    out-of-set values. Returns the cleaned dict ready to merge."""
    cleaned: dict[str, Any] = {}
    for k, v in patch.items():
        if k not in ALLOWED_VALUES:
            raise ValueError(f"unknown ui pref key: {k!r}")
        if v not in ALLOWED_VALUES[k]:
            raise ValueError(
                f"invalid value {v!r} for {k!r}; "
                f"allowed: {sorted(ALLOWED_VALUES[k])}"
            )
        cleaned[k] = v
    return cleaned
