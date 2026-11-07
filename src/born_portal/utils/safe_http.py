"""SSRF-safe HTTP fetching.

The URL validator in :mod:`born_portal.utils.url_guard` only checks a URL
before it is used. Two gaps remain when the fetch layer follows redirects and
performs its own DNS lookup:

* A redirect can point at an internal address that was never validated.
* A hostname can be re-bound to an internal address between validation and
  connection (DNS rebinding).

:func:`get_public` closes both. It follows redirects manually, validating
every hop, and connects through :class:`GuardedNetworkBackend`, which resolves
each target just before connecting and opens the socket against the verified
numeric address. TLS SNI/certificate verification still uses the original
hostname because that is handled above the network backend.
"""

from __future__ import annotations

import typing
from urllib.parse import urljoin

import httpcore2
import httpx2
from httpcore2._backends.anyio import AnyIOBackend
from httpcore2._backends.base import SOCKET_OPTION, AsyncNetworkStream

from born_portal.utils.url_guard import (
    UnsafeURLError,
    resolve_public_addresses,
    validate_public_http_url,
)

MAX_REDIRECTS = 10


class GuardedNetworkBackend(AnyIOBackend):
    """TCP backend that pins connections to previously validated public IPs.

    httpcore resolves ``host`` itself during ``connect_tcp``. We instead look
    up the hostname here, reject any non-public result, and dial a verified
    numeric address. Because no second name lookup happens, a hostname cannot
    be rebound to an internal address after validation.
    """

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        addresses = resolve_public_addresses(host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await super().connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore2.ConnectError, httpcore2.ConnectTimeout) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error


class SafeAsyncHTTPTransport(httpx2.AsyncHTTPTransport):
    """An AsyncHTTPTransport whose TCP connections are SSRF-validated."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Replace the pool's default backend so every connection (including
        # proxy-free redirect hops) is validated at connect time. The pool is
        # built by the base class with all options already applied; we only
        # swap the network backend, which is used per connection attempt.
        self._pool._network_backend = GuardedNetworkBackend()


async def get_public(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    allowed_hosts: set[str] | None = None,
    timeout: float = 30.0,
    max_redirects: int = MAX_REDIRECTS,
) -> httpx2.Response:
    """GET a public URL, validating the target and every redirect hop.

    ``allowed_hosts`` (when given) restricts every hop to an explicit host
    allow-list. Raises :class:`UnsafeURLError` for a non-public or disallowed
    target, or when too many redirects are followed.
    """
    current = validate_public_http_url(url, allowed_hosts=allowed_hosts)
    transport = SafeAsyncHTTPTransport()
    async with httpx2.AsyncClient(
        transport=transport,
        timeout=timeout,
        headers=headers or {},
        follow_redirects=False,
    ) as client:
        for _ in range(max_redirects + 1):
            response = await client.get(current)

            location = response.headers.get("location")
            if not response.is_redirect or not location:
                response.raise_for_status()
                return response

            current = validate_public_http_url(
                urljoin(current, location), allowed_hosts=allowed_hosts
            )

    raise UnsafeURLError(f"Too many redirects fetching: {url}")
