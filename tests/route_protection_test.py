"""Guard against the fail-open authorization model.

Authorization relies entirely on per-handler ``@auth``/``@allow_anonymous``
decorators: the default authorization policy permits anonymous access unless a
handler is explicitly decorated. These tests assert that every registered route
is decorated and that the anonymous-accessible surface matches expectations, so
a route added without a decorator (or an over-broad ``@allow_anonymous``) fails
the suite.
"""

import os

# Each Application gets its own Router so importing the real app doesn't collide
# with the throwaway Applications other tests build via the shared default router.
os.environ["APP_DEFAULT_ROUTER"] = "0"

from born_portal.main import app

# Handler names that are intentionally reachable by anonymous users.
_PUBLIC_HANDLERS = {
    "login_page",
    "auth_google",
    "auth_callback",
    "logout",
    "podcast_audio",
    "shows_video",
    "manifest",
    "icon_svg",
    "icon_180",
}


def _routes():
    return list(app.router.iter_all())


def test_every_route_is_explicitly_protected():
    unprotected = []
    for route in _routes():
        handler = route.handler
        if not (
            getattr(handler, "auth", False)
            or getattr(handler, "allow_anonymous", False)
        ):
            pattern = (
                route.full_pattern.decode()
                if isinstance(route.full_pattern, bytes)
                else route.full_pattern
            )
            unprotected.append(pattern)

    assert unprotected == [], (
        "Routes lack an explicit @auth(...) or @allow_anonymous() decorator:\n"
        + "\n".join(sorted(unprotected))
    )


def test_anonymous_surface_matches_expectations():
    anonymous = {
        getattr(r.handler, "__name__", "")
        for r in _routes()
        if getattr(r.handler, "allow_anonymous", False)
        and not getattr(r.handler, "auth", False)
    }
    assert anonymous == _PUBLIC_HANDLERS