"""SSRF guard — reject URLs that resolve to private/internal addresses.

Used by any code path that fetches a user-controlled URL (lead websites,
RSS feeds, etc.). Resolves the hostname and refuses loopback, private,
link-local (incl. cloud metadata 169.254.169.254), and reserved ranges.

Because DNS can be rebound between the check and the request, callers
should ALSO disable automatic redirect following and re-validate the host
of every redirect target (see `enrichment/sources/web_fetch.py`).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def is_public_host(host: str) -> bool:
    """True only if every resolved address for `host` is a public IP."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for *_, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def is_safe_fetch_url(url: str) -> bool:
    """True if `url` is an http(s) URL whose host resolves to a public IP."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.hostname:
        return False
    return is_public_host(parsed.hostname)
