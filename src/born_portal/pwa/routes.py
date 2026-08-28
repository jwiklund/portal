from pathlib import Path

import aiofiles
from blacksheep import Request, Response
from blacksheep.contents import Content
from blacksheep.server.responses import json

HERE = Path(__file__).parent


def register_routes(app):
    @app.router.get("/manifest.json")
    async def manifest(request: Request):
        return json(
            {
                "name": "Portal",
                "short_name": "Portal",
                "start_url": "/",
                "display": "standalone",
                "orientation": "portrait",
                "icons": [
                    {
                        "src": "/icon.svg",
                        "sizes": "512x512",
                        "type": "image/svg+xml",
                    },
                ],
            }
        )

    @app.router.get("/icon.svg")
    async def icon_svg(request: Request):
        async with aiofiles.open(HERE / "icon.svg", "rb") as f:
            return Response(200, content=Content(b"image/svg+xml", await f.read()))

    @app.router.get("/icon-180.png")
    async def icon_180(request: Request):
        async with aiofiles.open(HERE / "icon-180.png", "rb") as f:
            return Response(200, content=Content(b"image/png", await f.read()))
