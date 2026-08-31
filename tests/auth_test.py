import asyncio

import pytest
from blacksheep import Application, Response
from blacksheep.server.authentication import get_authentication_middleware
from blacksheep.server.authorization import auth, get_authorization_middleware
from blacksheep.sessions import Session
from guardpost.authorization import AuthorizationError

from born_portal.auth.guard import SessionAuthHandler, authenticate_failed_redirect
from born_portal.core import ADMIN_ROLE, ADMIN_USERS, VIEW_USERS


class FakeRequest:
    def __init__(self, user: str | None):
        self.session = Session({"user": user} if user else {})
        self.path = "/x"
        self.method = "GET"
        self._user = None

    @property
    def identity(self):
        return self._user

    @identity.setter
    def identity(self, value):
        self._user = value

    @property
    def user(self):
        return self._user


async def passthrough(request):
    return Response(200)


def run_auth(email, handler):
    app = Application()
    authn = app.use_authentication().add(SessionAuthHandler(ADMIN_USERS, VIEW_USERS))
    app.use_authorization()
    request = FakeRequest(email)
    asyncio.run(get_authentication_middleware(authn)(request, passthrough))
    middleware = get_authorization_middleware(app._authorization_strategy)
    return asyncio.run(middleware(request, handler))


def test_admin_role_assignment():
    h = SessionAuthHandler({"a@x"}, {"v@x"})
    identity = asyncio.run(h.authenticate(FakeRequest("a@x")))
    assert identity is not None
    assert identity.roles == [ADMIN_ROLE, "viewer"]


def test_viewer_role_assignment():
    h = SessionAuthHandler({"a@x"}, {"v@x"})
    identity = asyncio.run(h.authenticate(FakeRequest("v@x")))
    assert identity is not None
    assert identity.roles == ["viewer"]


def test_anonymous_gets_no_identity():
    h = SessionAuthHandler({"a@x"}, {"v@x"})
    assert asyncio.run(h.authenticate(FakeRequest(None))) is None


def test_admin_can_reach_admin_page():
    admin_email = next(iter(ADMIN_USERS))

    @auth(roles=[ADMIN_ROLE])
    async def admin_page(request):
        return Response(200)

    assert run_auth(admin_email, admin_page).status == 200


def test_viewer_denied_admin_page():
    viewer_email = next(iter(VIEW_USERS))

    @auth(roles=[ADMIN_ROLE])
    async def admin_page(request):
        return Response(200)

    with pytest.raises(AuthorizationError):
        run_auth(viewer_email, admin_page)


def test_viewer_can_reach_view_page():
    viewer_email = next(iter(VIEW_USERS))

    @auth(roles=["viewer"])
    async def view_page(request):
        return Response(200)

    assert run_auth(viewer_email, view_page).status == 200


def test_admin_can_reach_view_page():
    admin_email = next(iter(ADMIN_USERS))

    @auth(roles=["viewer"])
    async def view_page(request):
        return Response(200)

    assert run_auth(admin_email, view_page).status == 200


def test_anonymous_denied_on_view_page():
    @auth(roles=["viewer"])
    async def view_page(request):
        return Response(200)

    with pytest.raises(AuthorizationError):
        run_auth(None, view_page)


def test_anonymous_redirects_to_login():
    result = asyncio.run(
        authenticate_failed_redirect(None, None, Exception("unauthorized"))
    )
    assert isinstance(result, Response)
    assert result.status == 302
    assert result.get_first_header(b"location") == b"/login"
