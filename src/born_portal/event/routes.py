from datetime import UTC, datetime

from blacksheep import Request
from blacksheep.server.responses import redirect

from born_portal import event
from born_portal.auth.guard import auth
from born_portal.core import ADMIN_ROLE, VIEWER_ROLE, form_value, render
from born_portal.event.model import EventData


def register_routes(app, engine):
    store = event.EventStore(engine)

    @app.router.get("/events")
    @auth(roles=[ADMIN_ROLE])
    async def events_list(request: Request, sort_by: str | None = None):
        all_events = store.list_all()

        today = datetime.now(UTC).date()
        today_str = today.isoformat()

        future_events = [e for e in all_events if e.date and e.date >= today_str]

        if sort_by == "price":
            future_events.sort(key=lambda e: (e.price or "", e.date or ""))
        else:
            future_events.sort(key=lambda e: e.date or "")

        def render_event(e: EventData) -> dict:
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

        upcoming = [render_event(e) for e in future_events[:20]]

        return render(
            "events.html",
            request,
            events=upcoming,
            sort_by=sort_by,
        )

    @app.router.get("/events/import")
    @auth(roles=[ADMIN_ROLE])
    async def events_import(request: Request):
        return render("events_import.html", request)

    @app.router.post("/events/import")
    @auth(roles=[ADMIN_ROLE])
    async def event_import(request: Request):
        form = await request.form()
        url = form_value(form, "url") or ""

        if not url:
            return render("events_import.html", request, error="Please enter a URL")

        try:
            event_data = await event.parse(url)
        except Exception as e:  # noqa: BLE001
            return render("events_import.html", request, error=str(e), url=url)

        # Check if event already exists by URL
        existing = store.get(url)
        if existing:
            return render(
                "event_edit.html",
                request,
                event=existing,
                from_import=True,
                is_update=True,
            )

        return render("event_edit.html", request, event=event_data, from_import=True)

    @app.router.get("/events/{event_id}")
    @auth(roles=[ADMIN_ROLE])
    async def event_detail(request: Request, event_id: int):
        event_data = store.get_by_id(event_id)
        if not event_data:
            return render("error.html", request, message="Event not found")

        return render(
            "event_detail.html",
            request,
            event=event_data,
        )

    @app.router.get("/events/edit/{event_id}")
    @auth(roles=[ADMIN_ROLE])
    async def event_edit(request: Request, event_id: int):
        event_data = store.get_by_id(event_id)
        if not event_data:
            return render("error.html", request, message="Event not found")

        return render("event_edit.html", request, event=event_data, from_import=False)

    @app.router.post("/events/save")
    @auth(roles=[ADMIN_ROLE])
    async def event_save(request: Request):
        form = await request.form()
        if not form:
            return render("error.html", request, message="No data provided")

        event_id = form_value(form, "event_id")
        # Determine if we're updating an existing event
        if event_id and event_id != "None":
            # Get existing event and update its fields
            existing = store.get_by_id(int(event_id))
            if existing:
                event_data = event.EventData(
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
                raise ValueError("Event does not exist")
        else:
            # No event_id, create new one
            event_data = event.EventData(
                url=form_value(form, "url") or "",
                name=form_value(form, "name") or "",
                description=form_value(form, "description") or "",
                location=form_value(form, "location"),
                price=form_value(form, "price"),
                date=form_value(form, "date"),
                ticket=form_value(form, "ticket") == "on",
            )
        event_id = store.save(event_data)

        return redirect(f"/events/{event_id}")

    @app.router.post("/events/delete")
    @auth(roles=[ADMIN_ROLE])
    async def event_delete(request: Request):
        form = await request.form()
        event_id = form_value(form, "event_id")

        if not event_id:
            return render("error.html", request, message="No event provided")

        # Get the URL before deleting
        event_data = store.get_by_id(int(event_id))
        if event_data:
            store.delete(event_data.url)

        return redirect("/events")

    @app.router.get("/events/{event_id}/view")
    @auth(roles=[VIEWER_ROLE])
    async def view_event_detail(request: Request, event_id: int):
        return await event_detail(request, event_id)

    @app.router.get("/events/view")
    @auth(roles=[VIEWER_ROLE])
    async def view_events_list(request: Request, sort_by: str | None = None):
        return await events_list(request, sort_by)
