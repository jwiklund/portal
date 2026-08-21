import asyncio

from born_portal.auth import AuthMiddleware

SENTINEL = object()


class FakeRequest:
    def __init__(self, path: str, method: str = "GET", user: str | None = None):
        self.path = path
        self.method = method
        self.session = {"user": user} if user else {}


async def passthrough_handler(request):
    return SENTINEL


def make_middleware():
    return AuthMiddleware(
        public_paths={"/login", "/auth/callback"},
        admin_users={"admin@example.com"},
        view_users={"viewer@example.com"},
    )


def call(middleware, request):
    return asyncio.run(middleware(request, passthrough_handler))


def test_public_path_passes_without_user():
    mw = make_middleware()
    resp = call(mw, FakeRequest("/login"))
    assert resp is SENTINEL


def test_no_user_redirects_to_login():
    mw = make_middleware()
    resp = call(mw, FakeRequest("/events"))
    assert resp is not SENTINEL


def test_admin_passes_anywhere():
    mw = make_middleware()
    for path in ("/events", "/podcasts", "/shows", "/festivals/edit/1"):
        resp = call(mw, FakeRequest(path, user="admin@example.com"))
        assert resp is SENTINEL, path


def test_viewer_get_on_view_pages():
    mw = make_middleware()
    for path in (
        "/events/view",
        "/events/3/view",
        "/festivals/view",
        "/festivals/7/view",
    ):
        resp = call(mw, FakeRequest(path, user="viewer@example.com"))
        assert resp is SENTINEL, path


def test_viewer_post_denied():
    mw = make_middleware()
    for path, method in (
        ("/festivals/save", "POST"),
        ("/events/view", "POST"),
    ):
        resp = call(mw, FakeRequest(path, method=method, user="viewer@example.com"))
        assert resp is not SENTINEL, path


def test_viewer_denied_non_view_pages():
    mw = make_middleware()
    for path in ("/podcasts", "/shows", "/events", "/events/3", "/events/import"):
        resp = call(mw, FakeRequest(path, user="viewer@example.com"))
        assert resp is not SENTINEL, path


def test_viewer_denied_admin_pages():
    mw = make_middleware()
    for path in (
        "/festivals/edit/1",
        "/festivals/new",
        "/festivals/api/spotify/search",
    ):
        resp = call(mw, FakeRequest(path, user="viewer@example.com"))
        assert resp is not SENTINEL, path


def test_unknown_user_denied():
    mw = make_middleware()
    resp = call(mw, FakeRequest("/events", user="stranger@example.com"))
    assert resp is not SENTINEL
