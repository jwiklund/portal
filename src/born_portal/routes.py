from blacksheep import Request

from born_portal.core import render


def user(request):
    email = request.session.get("user")
    return {"name": email.split("@")[0], "email": email}


def register_routes(app):
    @app.router.get("/")
    async def index(request: Request):
        return render("index.html", user=user(request))

    @app.router.get("/profile")
    async def profile(request: Request):
        return render("profile.html", user=user(request))
