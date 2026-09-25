"""Validation helpers to prevent server-side request forgery (SSRF)."""

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch server-side."""


def _check_ip(ip: str) -> None:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError as e:
        raise UnsafeURLError(f"Could not parse resolved address: {ip}") from e
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    ):
        raise UnsafeURLError(f"Refusing to fetch non-public address: {ip}")


def validate_public_http_url(url: str, *, allowed_hosts: set[str] | None = None) -> str:
    """Validate that url is a safe http(s) URL to fetch server-side.

    - Scheme must be http or https.
    - Hostname must be present (optionally restricted to allowed_hosts).
    - All resolved IP addresses must be public (no loopback, private,
      link-local, reserved, multicast or unspecified addresses).

    Returns the URL if safe, raises UnsafeURLError otherwise.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Only http(s) URLs are allowed: {url}")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError(f"URL has no hostname: {url}")

    if allowed_hosts is not None and hostname not in allowed_hosts:
        raise UnsafeURLError(f"Host not allowed: {hostname}")

    try:
        infos = socket.getaddrinfo(
            hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except OSError as e:
        raise UnsafeURLError(f"Could not resolve host: {hostname}") from e

    seen: set[str] = set()
    for info in infos:
        addr = str(info[4][0])
        if addr not in seen:
            seen.add(addr)
            _check_ip(addr)

    return url
