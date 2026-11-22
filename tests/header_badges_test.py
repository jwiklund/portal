"""Header links and alert markers for admins (unread notifications, errors)."""

import asyncio

from born_portal import core
from born_portal.utils.headers import (
    ERROR,
    NOTIFICATION,
    Attention,
    HeaderProvider,
)


class _Request:
    def __init__(self, email: str, provider: HeaderProvider, path: str = "/upcoming"):
        self.session = {"user": email}
        self.path = path
        self.header_provider = provider


def _body(monkeypatch, email: str, provider: HeaderProvider, path="/upcoming") -> str:
    monkeypatch.setattr(core, "ADMIN_USERS", {"admin@example.com"})
    return asyncio.run(
        core.render(
            "notifications.html",
            _Request(email, provider, path),
            notifications=[],
            new_ids=set(),
            new_count=0,
            push_configured=False,
        )
    ).content.body.decode()


def _attention(kind: str, count: int, label: str):
    async def read():
        if count <= 0:
            return None
        return Attention(kind, label)

    return read


def test_admin_header_shows_blue_and_red_markers(monkeypatch):
    provider = HeaderProvider()
    provider.register(
        "/notifications",
        "Notifications",
        section="menu",
        attention=_attention(NOTIFICATION, 2, "unread notifications"),
        admin_only=True,
    )
    provider.register(
        "/errors",
        "Errors",
        section="menu",
        attention=_attention(ERROR, 1, "recorded error"),
        admin_only=True,
    )

    body = _body(monkeypatch, "admin@example.com", provider)

    assert "nav-badge-notification" in body
    assert "unread notifications" in body
    assert "nav-badge-error" in body
    assert "recorded error" in body


def test_admin_header_hides_markers_when_clear(monkeypatch):
    provider = HeaderProvider()
    provider.register(
        "/notifications",
        "Notifications",
        section="menu",
        attention=_attention(NOTIFICATION, 0, "unread notification"),
        admin_only=True,
    )
    provider.register(
        "/errors",
        "Errors",
        section="menu",
        attention=_attention(ERROR, 0, "recorded error"),
        admin_only=True,
    )

    body = _body(monkeypatch, "admin@example.com", provider)

    assert 'class="nav-badge' not in body


def test_viewer_sees_viewer_paths_and_no_admin_links(monkeypatch):
    provider = HeaderProvider()
    provider.register("/upcoming", "Upcoming", viewer_path="/upcoming/view")
    provider.register("/playlists", "Playlists", admin_only=True)
    provider.register("/errors", "Errors", section="menu", admin_only=True)

    body = _body(monkeypatch, "viewer@example.com", provider)

    assert 'href="/upcoming/view"' in body
    assert "Playlists" not in body
    assert "Errors" not in body


def test_links_follow_registration_order():
    provider = HeaderProvider()
    provider.register("/late", "Late", order=20)
    provider.register("/early", "Early", order=10)

    context = asyncio.run(provider.context(is_admin=True, current_path="/"))

    assert [link.name for link in context["header_main"]] == ["Early", "Late"]


def test_attention_callables_run_concurrently():
    async def run():
        second_ran = asyncio.Event()

        async def first():
            # Only resolves if the second callable runs while this one is still
            # pending, i.e. the two are awaited concurrently.
            try:
                await asyncio.wait_for(second_ran.wait(), timeout=1)
            except TimeoutError:
                return None
            return Attention(NOTIFICATION, "unread notification")

        async def second():
            second_ran.set()

        provider = HeaderProvider()
        provider.register("/first", "First", attention=first, order=10)
        provider.register("/second", "Second", attention=second, order=20)
        return await provider.context(is_admin=True, current_path="/")

    context = asyncio.run(run())

    assert [link.name for link in context["header_main"]] == ["First", "Second"]
    assert context["header_main"][0].attention is not None


def test_broken_attention_counter_does_not_break_page(monkeypatch):
    recorded = []

    async def report(request, exc, link):
        recorded.append((request, exc, link))

    async def attention():
        raise RuntimeError("database unavailable")

    provider = HeaderProvider(report_error=report)
    provider.register(
        "/errors",
        "Errors",
        section="menu",
        attention=attention,
        admin_only=True,
    )

    body = _body(monkeypatch, "admin@example.com", provider)

    assert "Errors" in body
    assert 'class="nav-badge' not in body
    assert len(recorded) == 1
    request, exc, link = recorded[0]
    assert request.path == "/upcoming"
    assert isinstance(exc, RuntimeError)
    assert link == "/errors"


def test_failing_error_reporter_does_not_break_page(monkeypatch):
    async def report(request, exc, link):
        raise RuntimeError("error log unavailable")

    async def attention():
        raise RuntimeError("database unavailable")

    provider = HeaderProvider(report_error=report)
    provider.register(
        "/errors",
        "Errors",
        section="menu",
        attention=attention,
        admin_only=True,
    )

    body = _body(monkeypatch, "admin@example.com", provider)

    assert "Errors" in body
    assert 'class="nav-badge' not in body
