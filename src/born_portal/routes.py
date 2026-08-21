from born_portal.core import is_viewer, render, user
from born_portal.event import biletto, model, store

__all__ = ["biletto", "model", "store"]

from blacksheep.server.responses import redirect


def register_routes(app):
    @app.router.get("/")
    async def index(request):
        if is_viewer(request):
            return redirect("/events/view")
        return redirect("/events")
