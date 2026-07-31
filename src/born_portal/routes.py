from born_portal.core import render, user
from born_portal.event import biletto, model, store

__all__ = ["biletto", "model", "store", "register_event_routes"]

from blacksheep.server.responses import redirect


def register_routes(app):
    @app.router.get("/")
    async def index(request):
        return redirect("/events")
