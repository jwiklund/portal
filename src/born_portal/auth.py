from blacksheep import Request, Response
from blacksheep.contents import TextContent
from blacksheep.server.responses import redirect
from typing import Callable, Awaitable


class AuthMiddleware:
    def __init__(self, public_paths: set[str], allowed_users: set[str]):
        self._public = public_paths or {"/login", "/auth/google", "/auth/callback"}
        self._allowed_users = allowed_users

    async def __call__(
        self, request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.path in self._public:
            return await handler(request)

        if not request.session.get("user"):
            return redirect("/login")

        if request.session.get("user", {}).get("email") not in self._allowed_users:
            return Response(403, content=TextContent("Forbidden"))

        return await handler(request)
