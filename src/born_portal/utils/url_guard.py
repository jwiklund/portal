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
    # Unwrap IPv4-mapped IPv6 addresses (e.g. "::ffff:127.0.0.1") so their
    # embedded IPv4 address is classified correctly.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
        or not addr.is_global
    ):
        raise UnsafeURLError(f"Refusing to fetch non-public address: {ip}")


def resolve_public_addresses(hostname: str, port: int) -> list[str]:
    """Resolve hostname, returning every address once all are verified public.

    Raises UnsafeURLError if the name cannot be resolved or any resolved
    address is not globally routable. The caller is expected to connect to one
    of the returned numeric addresses directly, which prevents DNS rebinding
    between validation and connection.
    """
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise UnsafeURLError(f"Could not resolve host: {hostname}") from e

    addresses: list[str] = []
    for info in infos:
        addr = str(info[4][0])
        if addr in addresses:
            continue
        _check_ip(addr)
        addresses.append(addr)

    if not addresses:
        raise UnsafeURLError(f"Could not resolve host: {hostname}")

    return addresses


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

    resolve_public_addresses(
        hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    )

    return url
