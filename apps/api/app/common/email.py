"""Email normalization + corporate-domain extraction — Odoo dedup pattern.

`normalize_email`  → trimmed, lower-cased address; the dedup key for the *full*
                     email and a stable match key across channels.
`email_domain_criterion` → the *corporate* domain, with free-mail providers
                     (gmail, yandex, mail.ru, …) excluded. So two different
                     people at the same company (`ivan@acme.ru`, `petr@acme.ru`)
                     are flagged as duplicates, but two gmail users are not.
"""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Consumer / free-mail domains: shared by unrelated people, so NOT a usable
# corporate-dedup signal.
FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com", "googlemail.com",
        "yandex.ru", "ya.ru", "yandex.com",
        "mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru",
        "rambler.ru", "lenta.ru", "autorambler.ru", "ro.ru",
        "yahoo.com", "ymail.com",
        "outlook.com", "hotmail.com", "live.com", "live.ru", "msn.com",
        "icloud.com", "me.com", "mac.com",
        "proton.me", "protonmail.com",
        "gmx.com", "gmx.net", "aol.com", "zoho.com",
    }
)


def normalize_email(raw: str | None) -> str | None:
    """Trim + lower-case; return None if it is not a basic ``addr@host.tld``."""
    if not raw:
        return None
    candidate = raw.strip().lower()
    if not _EMAIL_RE.match(candidate):
        return None
    return candidate


def email_domain_criterion(email_normalized: str | None) -> str | None:
    """Corporate domain of a normalized email, or None for free-mail / invalid."""
    if not email_normalized or "@" not in email_normalized:
        return None
    domain = email_normalized.rsplit("@", 1)[1]
    if domain in FREEMAIL_DOMAINS:
        return None
    return domain
