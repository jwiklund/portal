"""Admin error log: the global exception handler and its browsing pages."""

from __future__ import annotations

import logging

from blacksheep import Request, Response
from blacksheep.contents import TextContent
from blacksheep.server.responses import redirect

from born_portal.auth.guard import auth
from born_portal.core import ADMIN_ROLE, render
from born_portal.errors.report import configure, record_error
from born_portal.errors.store import ErrorStore

logger = logging.getLogger(__name__)

# Shown to the user; the technical details are kept in the error log instead.
USER_ERROR_MESSAGE = (
    "Something went wrong while handling this request. "
    "The problem has been logged for review."
)


def register_routes(app, engine):
    store = ErrorStore(engine)
    # Make record_error() usable from route modules without threading the
    # engine through every handler.
    configure(engine)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(app, request, exc):
        # Registering a handler marks the exception as "handled", so BlackSheep
        # no longer logs it at ERROR level; do that here instead.
        logger.exception(
            "Unhandled exception - %s %s",
            request.method,
            request.url.value.decode("utf-8", "replace"),
        )
        await record_error(request, exc)
        try:
            return render("error.html", request, message=USER_ERROR_MESSAGE)
        except Exception:  # noqa: BLE001 - never mask the original error
            return Response(500, content=TextContent(USER_ERROR_MESSAGE))

    @app.router.get("/errors")
    @auth(roles=[ADMIN_ROLE])
    async def errors_list(request: Request):
        return render(
            "errors.html",
            request,
            errors=store.list_recent(),
            total=store.count(),
        )

    @app.router.get("/errors/{error_id}")
    @auth(roles=[ADMIN_ROLE])
    async def error_detail(request: Request, error_id: int):
        record = store.get_by_id(error_id)
        if record is None:
            return render("error.html", request, message="Error record not found")
        return render("error_detail.html", request, error=record)

    @app.router.post("/errors/clear")
    @auth(roles=[ADMIN_ROLE])
    async def errors_clear(request: Request):
        store.clear()
        return redirect("/errors")
