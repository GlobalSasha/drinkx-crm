"""Fence untrusted third-party text before it enters an LLM prompt (plan 014).

Brave result titles/descriptions, fetched website body, HH.ru vacancy text, and
inbound customer email subject+body are all attacker-influenced — anyone who
controls a scraped page, vacancy post, or inbound email can embed instructions
the LLM would otherwise follow. `wrap_untrusted` fences each block with explicit
delimiters and strips characters that could be used to escape the fence early.
"""
from __future__ import annotations

# Fence token unlikely to appear in ordinary Russian sales text or web content.
_FENCE_OPEN = "«UNTRUSTED:{label}»"
_FENCE_CLOSE = "«/UNTRUSTED:{label}»"
_ESCAPE_TARGET = "«/UNTRUSTED»"
_ESCAPE_NEUTRALIZED = "«/ U N T R U S T E D»"


def wrap_untrusted(label: str, text: str, max_chars: int | None = None) -> str:
    """Fence third-party text so the model treats it as DATA, not instructions.

    Strips control chars and neutralizes fence-escape attempts (a source trying
    to close our block early with a literal `«/UNTRUSTED»` token).
    """
    body = text or ""
    if max_chars is not None:
        body = body[:max_chars]
    body = body.replace(_ESCAPE_TARGET, _ESCAPE_NEUTRALIZED).replace("\x00", "")
    return f"{_FENCE_OPEN.format(label=label)}\n{body}\n{_FENCE_CLOSE.format(label=label)}"
