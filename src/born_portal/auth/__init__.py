"""Authentication and authorization for the portal app.

This package wires BlackSheep's built-in authentication/authorization strategies
(see https://www.neoteroi.dev/blacksheep/authorization/) so request handlers can
be annotated with access requirements via the ``@auth`` decorator.
"""

from born_portal.auth.guard import (
    allow_anonymous,
    auth,
    authenticate_failed_redirect,
    configure,
)
from born_portal.auth.middleware import AuthMiddleware, register_routes

__all__ = [
    "AuthMiddleware",
    "allow_anonymous",
    "auth",
    "authenticate_failed_redirect",
    "configure",
    "register_routes",
]