from __future__ import annotations

import json

from blacksheep import Request
from blacksheep.server.responses import json as json_response
from blacksheep.server.responses import redirect

from born_portal import past
from born_portal.auth.guard import auth
from born_portal.core import ADMIN_ROLE, VIEWER_ROLE, form_value, render
from born_portal.past.model import ArtistData, PastData
from born_portal.utils.date_range import parse_name_with_dates


def register_routes(app, engine):
    store = past.PastStore(engine)

    @app.router.get("/past")
    @auth(roles=[ADMIN_ROLE])
    async def past_list(request: Request):
        past_items = store.list_all()

        return render(
            "past.html",
            request,
            past=past_items,
        )

    @app.router.get("/past/view")
    @auth(roles=[VIEWER_ROLE])
    async def view_past_list(request: Request):
        return await past_list(request)

    @app.router.get("/past/new")
    @auth(roles=[ADMIN_ROLE])
    async def past_new(request: Request):
        known_album_uris = store.known_album_uris()

        return render(
            "past_edit.html",
            request,
            past=PastData(),
            known_album_uris=known_album_uris,
        )

    @app.router.get("/past/import")
    @auth(roles=[ADMIN_ROLE])
    async def past_import(request: Request):
        return render("past_import.html", request)

    @app.router.post("/past/import")
    @auth(roles=[ADMIN_ROLE])
    async def past_import_post(request: Request):
        form = await request.form()
        url = (form_value(form, "url") or "").strip()

        if not url:
            return render("past_import.html", request, error="Please enter a URL")

        try:
            page_html = await past.fetch_album_page(url)
            title = past.parse_album_title(page_html)
        except Exception as e:  # noqa: BLE001
            return render("past_import.html", request, error=str(e), url=url)

        name, start_date, end_date = parse_name_with_dates(title or "")

        known_album_uris = store.known_album_uris()

        return render(
            "past_edit.html",
            request,
            past=PastData(
                name=name,
                start_date=start_date,
                end_date=end_date,
                album_uri=url,
            ),
            known_album_uris=known_album_uris,
        )

    @app.router.get("/past/edit/{past_id}")
    @auth(roles=[ADMIN_ROLE])
    async def past_edit(request: Request, past_id: int):
        past_data = store.get_by_id(past_id)
        known_album_uris = store.known_album_uris()

        if not past_data:
            return render("error.html", request, message="Past item not found")

        return render(
            "past_edit.html",
            request,
            past=past_data,
            known_album_uris=known_album_uris,
        )

    @app.router.get("/past/api/spotify/search")
    @auth(roles=[ADMIN_ROLE])
    async def spotify_search(request: Request):
        params = dict(request.query)
        query = (params.get("q", [""])[0] or "").strip()
        if not query:
            return json_response({"artists": []})

        try:
            artists = await past.search_artists(query)
        except Exception as e:  # noqa: BLE001
            return json_response({"error": str(e)}, status=502)

        return json_response({"artists": artists})

    @app.router.get("/past/{past_id}")
    @auth(roles=[ADMIN_ROLE])
    async def past_detail(request: Request, past_id: int):
        past_data = store.get_by_id(past_id)

        if not past_data:
            return render("error.html", request, message="Past item not found")

        photos = []
        album_error = None
        if past_data.album_uri:
            try:
                photos = await past.fetch_album_photos(past_data.album_uri)
            except Exception as e:  # noqa: BLE001
                album_error = f"Could not load album: {e}"

        return render(
            "past_detail.html",
            request,
            past=past_data,
            photos=photos,
            album_error=album_error,
        )

    @app.router.get("/past/{past_id}/view")
    @auth(roles=[VIEWER_ROLE])
    async def view_past_detail(request: Request, past_id: int):
        return await past_detail(request, past_id)

    @app.router.post("/past/save")
    @auth(roles=[ADMIN_ROLE])
    async def past_save(request: Request):
        form = await request.form()
        if not form:
            return render("error.html", request, message="No data provided")

        name = (form_value(form, "name") or "").strip()
        if not name:
            return render("error.html", request, message="Name is required")

        artists = []
        try:
            raw = json.loads(form_value(form, "artists_json") or "[]")
            artists = [
                ArtistData(
                    name=item.get("name", ""), spotify_uri=item.get("spotify_uri")
                )
                for item in raw
                if item.get("name", "").strip()
            ]
        except (json.JSONDecodeError, AttributeError):
            return render("error.html", request, message="Invalid artist data")

        past_id = form_value(form, "past_id")
        past_data = PastData(
            id=int(past_id) if past_id else None,
            name=name,
            start_date=form_value(form, "start_date") or None,
            end_date=form_value(form, "end_date") or None,
            location=(form_value(form, "location") or "").strip() or None,
            description=form_value(form, "description") or "",
            album_uri=(form_value(form, "album_uri") or "").strip() or None,
            artists=artists,
        )

        saved_id = store.save(past_data)

        return redirect(f"/past/{saved_id}")

    @app.router.post("/past/delete")
    @auth(roles=[ADMIN_ROLE])
    async def past_delete(request: Request):
        form = await request.form()
        past_id = form_value(form, "past_id")
        if not past_id:
            return render("error.html", request, message="No item provided")

        store.delete(int(past_id))

        return redirect("/past")
