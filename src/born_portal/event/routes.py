from datetime import datetime
from typing import Optional

from blacksheep import Request, Response
from blacksheep.server.responses import redirect

from born_portal import event
from born_portal.core import render


def user(request: Request) -> dict:
    email = request.session.get("user")
    return {"name": email.split("@")[0], "email": email}


def register_routes(app):
    @app.router.get("/events")
    async def events_list(request: Request, sort_by: Optional[str] = None):
        store = event.EventStore()
        try:
            all_events = store.list_all()
        finally:
            store.close()

        today = datetime.now().date()
        today_str = today.isoformat()

        future_events = [e for e in all_events if e.date and e.date >= today_str]

        if sort_by == "price":
            future_events.sort(key=lambda e: (e.price or "", e.date or ""))
        else:
            future_events.sort(key=lambda e: e.date or "")

        upcoming = future_events[:20]

        return render("events.html", user=user(request), events=upcoming)

    @app.router.get("/events/import")
    async def events_import(request: Request):
        return render("events_import.html", user=user(request))

    @app.router.post("/events/import")
    async def event_import(request: Request):
        form = await request.form()
        url = form.get("url", "")

        if not url:
            return render(
                "events_import.html", user=user(request), error="Please enter a URL"
            )

        try:
            event_data = await event.parse(url)
        except Exception as e:
            return render(
                "events_import.html", user=user(request), error=str(e), url=url
            )

        # Check if event already exists by URL
        store = event.EventStore()
        try:
            existing = store.get(url)
        finally:
            store.close()

        if existing:
            return render(
                "event_edit.html",
                user=user(request),
                event=existing,
                from_import=True,
                is_update=True,
            )

        return render(
            "event_edit.html", user=user(request), event=event_data, from_import=True
        )

    @app.router.get("/events/{event_id}")
    async def event_detail(request: Request, event_id: int):
        store = event.EventStore()
        try:
            event_data = store.get_by_id(event_id)
            if not event_data:
                return render(
                    "error.html", user=user(request), message="Event not found"
                )
            # Store original URL for redirect
            event_url = event_data.url
        finally:
            store.close()

        return render("event_detail.html", user=user(request), event=event_data)

    @app.router.get("/events/edit/{event_id}")
    async def event_edit(request: Request, event_id: int):
        store = event.EventStore()
        try:
            event_data = store.get_by_id(event_id)
            if not event_data:
                return render(
                    "error.html", user=user(request), message="Event not found"
                )
        finally:
            store.close()

        return render(
            "event_edit.html", user=user(request), event=event_data, from_import=False
        )

    @app.router.post("/events/save")
    async def event_save(request: Request):
        form = await request.form()
        if not form:
            return render("error.html", user=user(request), message="No data provided")

        store = event.EventStore()
        try:
            event_id = form.get("event_id")

            # Determine if we're updating an existing event
            if event_id:
                # Get existing event and update its fields
                existing = store.get_by_id(int(event_id))
                if existing:
                    event_data = event.EventData(
                        id=existing.id,
                        url=existing.url,  # Preserve original URL
                        name=form.get("name", ""),
                        description=form.get("description", ""),
                        location=form.get("location"),
                        price=form.get("price"),
                        date=form.get("date"),
                        ticket=bool(form.get("ticket") == "on"),
                    )
                else:
                    raise Exception("Event does not exist")
            else:
                # No event_id, create new one
                event_data = event.EventData(
                    url=form.get("url", ""),
                    name=form.get("name", ""),
                    description=form.get("description", ""),
                    location=form.get("location"),
                    price=form.get("price"),
                    date=form.get("date"),
                    ticket=ticket,
                )
            event_id = store.save(event_data)
        finally:
            store.close()

        print(event_id)

        return redirect(f"/events/{event_id}")

    @app.router.post("/events/delete")
    async def event_delete(request: Request):
        form = await request.form()
        event_id = form.get("event_id")

        if not event_id:
            return render("error.html", user=user(request), message="No event provided")

        store = event.EventStore()
        try:
            # Get the URL before deleting
            event_data = store.get_by_id(int(event_id))
            if event_data:
                store.delete(event_data.url)
        finally:
            store.close()

        return redirect("/events")
