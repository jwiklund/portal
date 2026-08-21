from __future__ import annotations

import json

from blacksheep import Request
from blacksheep.server.responses import json as json_response
from blacksheep.server.responses import redirect

from born_portal import festival
from born_portal.core import render
from born_portal.festival.model import ArtistData, FestivalData
from born_portal.utils.date_range import parse_name_with_dates


def register_routes(app):
    @app.router.get("/festivals")
    async def festivals_list(request: Request):
        store = festival.FestivalStore()
        try:
            festivals = store.list_all()
        finally:
            store.close()

        return render(
            "festivals.html",
            request,
            festivals=festivals,
        )

    @app.router.get("/festivals/view")
    async def view_festivals_list(request: Request):
        return await festivals_list(request)

    @app.router.get("/festivals/new")
    async def festival_new(request: Request):
        store = festival.FestivalStore()
        try:
            known_album_uris = store.known_album_uris()
        finally:
            store.close()

        return render(
            "festival_edit.html",
            request,
            festival=FestivalData(),
            known_album_uris=known_album_uris,
        )

    @app.router.get("/festivals/import")
    async def festival_import(request: Request):
        return render("festival_import.html", request)

    @app.router.post("/festivals/import")
    async def festival_import_post(request: Request):
        form = await request.form()
        url = (form.get("url") or "").strip()

        if not url:
            return render("festival_import.html", request, error="Please enter a URL")

        try:
            page_html = await festival.fetch_album_page(url)
            title = festival.parse_album_title(page_html)
        except Exception as e:
            return render("festival_import.html", request, error=str(e), url=url)

        name, start_date, end_date = parse_name_with_dates(title or "")

        store = festival.FestivalStore()
        try:
            known_album_uris = store.known_album_uris()
        finally:
            store.close()

        return render(
            "festival_edit.html",
            request,
            festival=FestivalData(
                name=name,
                start_date=start_date,
                end_date=end_date,
                album_uri=url,
            ),
            known_album_uris=known_album_uris,
        )

    @app.router.get("/festivals/edit/{festival_id}")
    async def festival_edit(request: Request, festival_id: int):
        store = festival.FestivalStore()
        try:
            festival_data = store.get_by_id(festival_id)
            known_album_uris = store.known_album_uris()
        finally:
            store.close()

        if not festival_data:
            return render("error.html", request, message="Festival not found")

        return render(
            "festival_edit.html",
            request,
            festival=festival_data,
            known_album_uris=known_album_uris,
        )

    @app.router.get("/festivals/api/spotify/search")
    async def spotify_search(request: Request):
        params = dict(request.query)
        query = (params.get("q", [""])[0] or "").strip()
        if not query:
            return json_response({"artists": []})

        try:
            artists = await festival.search_artists(query)
        except Exception as e:
            return json_response({"error": str(e)}, status=502)

        return json_response({"artists": artists})

    @app.router.get("/festivals/{festival_id}")
    async def festival_detail(request: Request, festival_id: int):
        store = festival.FestivalStore()
        try:
            festival_data = store.get_by_id(festival_id)
        finally:
            store.close()

        if not festival_data:
            return render("error.html", request, message="Festival not found")

        photos = []
        album_error = None
        if festival_data.album_uri:
            try:
                photos = await festival.fetch_album_photos(festival_data.album_uri)
            except Exception as e:
                album_error = f"Could not load album: {e}"

        return render(
            "festival_detail.html",
            request,
            festival=festival_data,
            photos=photos,
            album_error=album_error,
        )

    @app.router.get("/festivals/{festival_id}/view")
    async def view_festival_detail(request: Request, festival_id: int):
        return await festival_detail(request, festival_id)

    @app.router.post("/festivals/save")
    async def festival_save(request: Request):
        form = await request.form()
        if not form:
            return render("error.html", request, message="No data provided")

        name = (form.get("name") or "").strip()
        if not name:
            return render("error.html", request, message="Festival name is required")

        artists = []
        try:
            raw = json.loads(form.get("artists_json") or "[]")
            artists = [
                ArtistData(
                    name=item.get("name", ""), spotify_uri=item.get("spotify_uri")
                )
                for item in raw
                if item.get("name", "").strip()
            ]
        except (json.JSONDecodeError, AttributeError):
            return render("error.html", request, message="Invalid artist data")

        festival_id = form.get("festival_id")
        festival_data = FestivalData(
            id=int(festival_id) if festival_id else None,
            name=name,
            start_date=form.get("start_date") or None,
            end_date=form.get("end_date") or None,
            location=(form.get("location") or "").strip() or None,
            description=form.get("description") or "",
            album_uri=(form.get("album_uri") or "").strip() or None,
            artists=artists,
        )

        store = festival.FestivalStore()
        try:
            saved_id = store.save(festival_data)
        finally:
            store.close()

        return redirect(f"/festivals/{saved_id}")

    @app.router.post("/festivals/delete")
    async def festival_delete(request: Request):
        form = await request.form()
        festival_id = form.get("festival_id")
        if not festival_id:
            return render("error.html", request, message="No festival provided")

        store = festival.FestivalStore()
        try:
            store.delete(int(festival_id))
        finally:
            store.close()

        return redirect("/festivals")
