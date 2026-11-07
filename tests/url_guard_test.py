"""Tests for SSRF protections: URL validation and redirect handling."""

from __future__ import annotations

import socket
import types

import pytest

from born_portal.utils import safe_http, url_guard
from born_portal.utils.url_guard import (
    UnsafeURLError,
    resolve_public_addresses,
    validate_public_http_url,
)

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def fake_dns(monkeypatch):
    """Map any hostname to a public IP, except 'internal.test'."""

    def getaddrinfo(host, port, *args, **kwargs):
        ip = "127.0.0.1" if host == "internal.test" else PUBLIC_IP
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))
        ]

    monkeypatch.setattr(url_guard.socket, "getaddrinfo", getaddrinfo)


def test_validate_rejects_scheme(fake_dns):
    with pytest.raises(UnsafeURLError):
        validate_public_http_url("file:///etc/passwd")


def test_validate_rejects_internal_address(fake_dns):
    with pytest.raises(UnsafeURLError):
        validate_public_http_url("http://internal.test/")


def test_validate_accepts_public_address(fake_dns):
    assert validate_public_http_url("https://example.com/") == "https://example.com/"


def test_validate_rejects_allowed_host_mismatch(fake_dns):
    with pytest.raises(UnsafeURLError):
        validate_public_http_url("https://example.com/", allowed_hosts={"other.test"})


def test_resolve_rejects_ipv4_mapped_loopback(fake_dns):
    with pytest.raises(UnsafeURLError):
        # ::ffff:127.0.0.1 embeds a loopback IPv4 address.
        url_guard._check_ip("::ffff:127.0.0.1")


def test_resolve_public_addresses_returns_validated(fake_dns):
    assert resolve_public_addresses("example.com", 443) == [PUBLIC_IP]


class _FakeResponse:
    def __init__(self, status_code, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")


class _FakeClient:
    """Scripted replacement for httpx2.AsyncClient used by get_public."""

    def __init__(self, responses, **kwargs):
        self._responses = list(responses)
        self.requested: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        self.requested.append(url)
        return self._responses.pop(0)


@pytest.fixture
def fake_client(monkeypatch):
    clients: list[_FakeClient] = []

    def build(responses):
        def factory(**kwargs):
            client = _FakeClient(responses, **kwargs)
            clients.append(client)
            return client

        monkeypatch.setattr(
            safe_http,
            "httpx2",
            types.SimpleNamespace(AsyncClient=factory),
        )
        return clients

    return build


def test_get_public_returns_final_response(fake_dns, fake_client):
    clients = fake_client(
        [
            _FakeResponse(302, {"location": "https://example.com/final"}),
            _FakeResponse(200, text="ok"),
        ]
    )
    response = _run(
        safe_http.get_public("https://example.com/start", headers={"UA": "x"})
    )
    assert response.text == "ok"
    assert clients[0].requested == [
        "https://example.com/start",
        "https://example.com/final",
    ]


def test_get_public_rejects_internal_redirect_target(fake_dns, fake_client):
    clients = fake_client(
        [_FakeResponse(302, {"location": "http://internal.test/latest/meta-data/"})]
    )
    with pytest.raises(UnsafeURLError):
        _run(safe_http.get_public("https://example.com/start"))
    # The internal target must never be requested.
    assert clients[0].requested == ["https://example.com/start"]


def test_get_public_enforces_allowed_hosts_on_redirect(fake_dns, fake_client):
    clients = fake_client([_FakeResponse(302, {"location": "https://other.test/path"})])
    with pytest.raises(UnsafeURLError):
        _run(
            safe_http.get_public(
                "https://example.com/start", allowed_hosts={"example.com"}
            )
        )
    assert clients[0].requested == ["https://example.com/start"]


def test_get_public_rejects_excessive_redirects(fake_dns, fake_client):
    redirect = _FakeResponse(302, {"location": "https://example.com/loop"})
    fake_client([redirect for _ in range(50)])
    with pytest.raises(UnsafeURLError):
        _run(safe_http.get_public("https://example.com/start", max_redirects=3))


def _run(coro):
    import asyncio

    return asyncio.run(coro)
