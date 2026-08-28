"""BlackSheep's built-in auth integration (see the authorization docs).

Bridges the signed session cookie (managed by AuthMiddleware) into a guardpost
``Identity`` so request handlers can be annotated with ``@auth`` requirements.

Anonymous calls that require authentication raise ``UnauthorizedError``, which is
mapped (below) to a redirect to the login page so the app keeps its redirect UX.
"""

from blacksheep import Request, Response
from blacksheep.server.authorization import UnauthorizedError, allow_anonymous, auth
from blacksheep.server.responses import redirect
from guardpost import AuthenticationHandler, Identity

from born_portal.core import ADMIN_ROLE, ADMIN_USERS, VIEW_USERS, VIEWER_ROLE

__all__ = ["allow_anonymous", "auth", "authenticate_failed_redirect", "configure"]


async def authenticate_failed_redirect(app, request, exc) -> Response:
    """Redirect anonymous users to the login page instead of returning 401."""
    return redirect("/login")


class SessionAuthHandler(AuthenticationHandler):
    """Builds a guardpost Identity from the signed session cookie."""

    def __init__(self, admin_users: set[str], view_users: set[str]):
        self._admin_users = admin_users
        self._view_users = view_users

    async def authenticate(self, context: Request) -> Identity | None:
        email = context.session.get("user")
        if email is None:
            return None

        roles = []
        if email in self._admin_users:
            # Admins may access view-only pages too, so they carry both roles.
            roles = [ADMIN_ROLE, VIEWER_ROLE]
        elif email in self._view_users:
            roles = [VIEWER_ROLE]

        return Identity({"email": email, "roles": roles}, "session")


def configure(app) -> None:
    """Wire BlackSheep's authentication and authorization strategies.

    ``use_authorization`` registers a default ``authenticated`` policy
    (AuthenticatedRequirement) that ``@auth(roles=[...])`` uses along with the
    specified roles, so no custom policies are needed.
    """
    app.use_authentication().add(SessionAuthHandler(ADMIN_USERS, VIEW_USERS))
    app.use_authorization()
    app.exceptions_handlers[UnauthorizedError] = authenticate_failed_redirect
