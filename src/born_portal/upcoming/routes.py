from datetime import UTC, datetime

from blacksheep import Request
from blacksheep.server.responses import redirect

from born_portal import upcoming
from born_portal.auth.guard import auth
from born_portal.core import ADMIN_ROLE, VIEWER_ROLE, form_value, render
from born_portal.upcoming.model import UpcomingData


def register_routes(app, engine):
    store = upcoming.UpcomingStore(engine)

    @app.router.get("/upcoming")
    @auth(roles=[ADMIN_ROLE])
    async def upcoming_list(request: Request, sort_by: str | None = None):
        all_upcoming = store.list_all()

        today = datetime.now(UTC).date()
        today_str = today.isoformat()

        future_upcoming = [e for e in all_upcoming if e.date and e.date >= today_str]

        if sort_by == "price":
            future_upcoming.sort(key=lambda e: (e.price or "", e.date or ""))
        else:
            future_upcoming.sort(key=lambda e: e.date or "")

        def render_upcoming(e: UpcomingData) -> dict:
            d = e.model_dump()
            i = d.get("date", "").find(" - ")
            if i != -1:
                d["date_end"] = d["date"][i + 3 :]
                d["date"] = d["date"][:i]
            else:
                i = d.get("date", "").find(" ")
                if i != -1:
                    d["date_end"] = d["date"][i + 1 :]
                    d["date"] = d["date"][:i]
            return d

        upcoming_items = [render_upcoming(e) for e in future_upcoming[:20]]

        return render(
            "upcoming.html",
            request,
            upcoming=upcoming_items,
            sort_by=sort_by,
        )

    @app.router.get("/upcoming/import")
    @auth(roles=[ADMIN_ROLE])
    async def upcoming_import(request: Request):
        return render("upcoming_import.html", request)

    @app.router.post("/upcoming/import")
    @auth(roles=[ADMIN_ROLE])
    async def upcoming_import_post(request: Request):
        form = await request.form()
        url = form_value(form, "url") or ""

        if not url:
            return render("upcoming_import.html", request, error="Please enter a URL")

        try:
            upcoming_data = await upcoming.parse(url)
        except Exception as e:  # noqa: BLE001
            return render("upcoming_import.html", request, error=str(e), url=url)

        # Check if the item already exists by URL
        existing = store.get(url)
        if existing:
            return render(
                "upcoming_edit.html",
                request,
                upcoming=existing,
                from_import=True,
                is_update=True,
            )

        return render(
            "upcoming_edit.html",
            request,
            upcoming=upcoming_data,
            from_import=True,
        )

    @app.router.get("/upcoming/{upcoming_id}")
    @auth(roles=[ADMIN_ROLE])
    async def upcoming_detail(request: Request, upcoming_id: int):
        upcoming_data = store.get_by_id(upcoming_id)
        if not upcoming_data:
            return render("error.html", request, message="Upcoming item not found")

        return render(
            "upcoming_detail.html",
            request,
            upcoming=upcoming_data,
        )

    @app.router.get("/upcoming/edit/{upcoming_id}")
    @auth(roles=[ADMIN_ROLE])
    async def upcoming_edit(request: Request, upcoming_id: int):
        upcoming_data = store.get_by_id(upcoming_id)
        if not upcoming_data:
            return render("error.html", request, message="Upcoming item not found")

        return render(
            "upcoming_edit.html", request, upcoming=upcoming_data, from_import=False
        )

    @app.router.post("/upcoming/save")
    @auth(roles=[ADMIN_ROLE])
    async def upcoming_save(request: Request):
        form = await request.form()
        if not form:
            return render("error.html", request, message="No data provided")

        upcoming_id = form_value(form, "upcoming_id")
        # Determine if we're updating an existing item
        if upcoming_id and upcoming_id != "None":
            # Get the existing item and update its fields
            existing = store.get_by_id(int(upcoming_id))
            if existing:
                upcoming_data = upcoming.UpcomingData(
                    id=existing.id,
                    url=existing.url,  # Preserve original URL
                    name=form_value(form, "name") or "",
                    description=form_value(form, "description") or "",
                    location=form_value(form, "location"),
                    price=form_value(form, "price"),
                    date=form_value(form, "date"),
                    ticket=form_value(form, "ticket") == "on",
                )
            else:
                raise ValueError("Upcoming item does not exist")
        else:
            # No id, create a new one
            upcoming_data = upcoming.UpcomingData(
                url=form_value(form, "url") or "",
                name=form_value(form, "name") or "",
                description=form_value(form, "description") or "",
                location=form_value(form, "location"),
                price=form_value(form, "price"),
                date=form_value(form, "date"),
                ticket=form_value(form, "ticket") == "on",
            )
        saved_id = store.save(upcoming_data)

        return redirect(f"/upcoming/{saved_id}")

    @app.router.post("/upcoming/delete")
    @auth(roles=[ADMIN_ROLE])
    async def upcoming_delete(request: Request):
        form = await request.form()
        upcoming_id = form_value(form, "upcoming_id")

        if not upcoming_id:
            return render("error.html", request, message="No upcoming item provided")

        # Get the URL before deleting
        upcoming_data = store.get_by_id(int(upcoming_id))
        if upcoming_data:
            store.delete(upcoming_data.url)

        return redirect("/upcoming")

    @app.router.get("/upcoming/{upcoming_id}/view")
    @auth(roles=[VIEWER_ROLE])
    async def view_upcoming_detail(request: Request, upcoming_id: int):
        return await upcoming_detail(request, upcoming_id)

    @app.router.get("/upcoming/view")
    @auth(roles=[VIEWER_ROLE])
    async def view_upcoming_list(request: Request, sort_by: str | None = None):
        return await upcoming_list(request, sort_by)
