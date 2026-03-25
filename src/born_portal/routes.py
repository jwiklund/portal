from blacksheep import Request
from born_portal.core import render


def register_routes(app):
    @app.router.get("/")
    async def index(request: Request):
        user = request.session.get("user")
        return render("index.html", user=user)

    @app.router.get("/profile")
    async def profile(request: Request):
        user = request.session.get("user")
        return render("profile.html", user=user)
