from blacksheep.server.responses import redirect

from born_portal.auth.guard import auth
from born_portal.core import is_viewer
from born_portal.event import biletto, model, store

__all__ = ["biletto", "model", "store"]


def register_routes(app):
    @app.router.get("/")
    @auth()
    async def index(request):
        if is_viewer(request):
            return redirect("/events/view")
        return redirect("/events")