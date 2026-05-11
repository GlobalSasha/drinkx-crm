"""Pure helpers for the companies domain.

`normalize_company_name` is the dedup key — collapses organisational
suffixes, quotes, and whitespace so «ООО "Аптека Апрель"» and
«АПТЕКА АПРЕЛЬ» land on the same row.

`extract_domain` peels protocol + `www.` off a freeform URL.

Both functions are pure and called from `services.py` only. They are
never invoked on values received from the frontend — payloads carry
`name` / `website`, and the service layer derives `normalized_name` /
`domain`.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

_ORG_FORMS = re.compile(
    r"\b(ооо|пао|оао|ао|зао|ип|нао|мсп|llc|ltd|inc|gmbh|s\.a|s\.r\.l|sarl)\b",
    flags=re.IGNORECASE | re.UNICODE,
)


def normalize_company_name(name: str) -> str:
    """Lower + strip quotes + drop org-forms + collapse whitespace.

    Used as the dedup key in `companies.normalized_name`. Order matters:
    quote stripping before org-form regex so an embedded suffix like
    «ООО "Foo"» drops both pieces.
    """
    s = (name or "").lower().strip()
    s = (
        s.replace("«", "")
        .replace("»", "")
        .replace('"', "")
        .replace("'", "")
    )
    s = _ORG_FORMS.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_domain(url: str | None) -> str | None:
    """`https://www.example.com/x` → `example.com`. Returns None on
    empty / unparseable input. Never raises — callers can pass any
    freeform website field."""
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = (parsed.hostname or "").removeprefix("www.").lower()
        return host or None
    except Exception:
        return None
