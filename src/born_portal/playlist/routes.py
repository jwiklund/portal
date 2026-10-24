from __future__ import annotations

from blacksheep import Request
from blacksheep.server.responses import json as json_response

from born_portal import playlist
from born_portal.auth.guard import auth
from born_portal.core import ADMIN_ROLE, form_value, render


def register_routes(app):
    @app.router.get("/playlists")
    @auth(roles=[ADMIN_ROLE])
    async def playlists_page(request: Request):
        return render("playlists.html", request, artists=[], tracks=[])

    @app.router.post("/playlists")
    @auth(roles=[ADMIN_ROLE])
    async def playlists_parse(request: Request):
        form = await request.form()
        url = (form_value(form, "url") or "").strip()
        text = form_value(form, "text") or ""

        if text.strip():
            try:
                artists, tracks = await playlist.extract_from_text(text)
            except Exception as e:  # noqa: BLE001
                return render(
                    "playlists.html",
                    request,
                    error=str(e),
                    text=text,
                    artists=[],
                    tracks=[],
                )

            return render(
                "playlists.html",
                request,
                artists=artists,
                tracks=tracks,
                text=text,
            )

        if not url:
            return render(
                "playlists.html",
                request,
                error="Please enter a URL or paste some text",
                artists=[],
                tracks=[],
            )

        try:
            artists, tracks = await playlist.extract(url)
        except Exception as e:  # noqa: BLE001
            return render(
                "playlists.html",
                request,
                error=str(e),
                url=url,
                artists=[],
                tracks=[],
            )

        return render(
            "playlists.html",
            request,
            artists=artists,
            tracks=tracks,
            url=url,
        )

    @app.router.get("/playlists/api/spotify/search")
    @auth(roles=[ADMIN_ROLE])
    async def playlist_spotify_search(request: Request):
        params = dict(request.query)
        query = (params.get("q", [""])[0] or "").strip()
        kind = (params.get("type", ["artist"])[0] or "artist").strip()

        if not query:
            return json_response({"results": []})

        try:
            if kind == "track":
                results = await playlist.search_tracks(query)
            else:
                results = await playlist.search_artists(query)
        except Exception as e:  # noqa: BLE001
            return json_response({"error": str(e)}, status=502)

        return json_response({"results": results})
