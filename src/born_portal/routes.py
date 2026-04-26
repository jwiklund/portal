from born_portal.core import render
from born_portal.event import biletto, model, store

__all__ = ["biletto", "model", "store", "register_event_routes"]


def user(request):
    email = request.session.get("user")
    return {"name": email.split("@")[0], "email": email}


def register_routes(app):
    @app.router.get("/")
    async def index(request):
        return render("index.html", user=user(request))

    @app.router.get("/profile")
    async def profile(request):
        return render("profile.html", user=user(request))
