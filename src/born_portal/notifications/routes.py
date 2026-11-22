"""Admin notifications: a browsable list plus a JSON API for adding entries."""

from __future__ import annotations

import html
import re

from blacksheep import Request
from blacksheep.server.responses import json as json_response
from blacksheep.server.responses import redirect

from born_portal import push
from born_portal.auth.guard import auth
from born_portal.core import ADMIN_ROLE, form_value, jinja, render
from born_portal.errors import record_error
from born_portal.notifications.model import Notification
from born_portal.notifications.store import NotificationStore
from born_portal.utils import headers

_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def linkify(text: str) -> str:
    """Escape ``text`` and turn bare http(s) URLs into safe links.

    Used as a Jinja filter: the escaped result is marked ``safe`` in the
    template so the anchors are not escaped again.
    """
    escaped = html.escape(text or "")

    def replace(match: re.Match[str]) -> str:
        url = match.group(0)
        trailing = ""
        while url and url[-1] in ".,;:!?)]":
            trailing = url[-1] + trailing
            url = url[:-1]
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
            f"{url}</a>{trailing}"
        )

    return _URL_RE.sub(replace, escaped)


def _parse_id(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _serialize(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "title": notification.title,
        "text": notification.text,
        "created_at": notification.created_at,
        "read": notification.read,
    }


def _push(notification: Notification | None) -> None:
    """Queue best-effort web-push delivery; it runs in the background so the
    request is not blocked by slow push-service calls."""
    if notification is not None:
        push.schedule_notification(notification)


def register_routes(app, engine, header):
    store = NotificationStore(engine)

    async def attention():
        count = store.unread_count()
        if count <= 0:
            return None
        label = "unread notification" if count == 1 else "unread notifications"
        return headers.Attention(headers.NOTIFICATION, label)

    header.register(
        "/notifications",
        "Notifications",
        section="menu",
        attention=attention,
        admin_only=True,
        order=60,
    )
    jinja.filters["linkify"] = linkify

    @app.router.get("/notifications")
    @auth(roles=[ADMIN_ROLE])
    async def notifications_list(request: Request):
        notifications = store.list_all()

        # Rendering the list counts as reading it: mark every shown
        # notification read, but keep the ids that were new so they can be
        # highlighted for this one view.
        new_ids = {n.id for n in notifications if not n.read and n.id is not None}
        store.mark_read_many(list(new_ids))
        for n in notifications:
            if n.id in new_ids:
                n.read = True

        return await render(
            "notifications.html",
            request,
            notifications=notifications,
            new_ids=new_ids,
            new_count=len(new_ids),
            push_configured=push.vapid_configured(),
        )

    @app.router.get("/notifications/new")
    @auth(roles=[ADMIN_ROLE])
    async def notifications_new(request: Request):
        return await render("notifications_new.html", request)

    @app.router.post("/notifications/add")
    @auth(roles=[ADMIN_ROLE])
    async def notifications_add(request: Request):
        form = await request.form()
        title = (form_value(form, "title") or "").strip()
        text = form_value(form, "text") or ""
        date = (form_value(form, "date") or "").strip() or None

        if title:
            notification_id, created = store.add_if_new(title, text, date)
            if created:
                _push(store.get_by_id(notification_id))

        return redirect("/notifications")

    @app.router.post("/notifications/read")
    @auth(roles=[ADMIN_ROLE])
    async def notifications_read(request: Request):
        form = await request.form()
        notification_id = _parse_id(form_value(form, "id"))
        read = (form_value(form, "read") or "1").strip() == "1"

        if notification_id is not None:
            store.set_read(notification_id, read)

        return redirect("/notifications")

    @app.router.post("/notifications/delete")
    @auth(roles=[ADMIN_ROLE])
    async def notifications_delete(request: Request):
        form = await request.form()
        notification_id = _parse_id(form_value(form, "id"))

        if notification_id is not None:
            store.delete(notification_id)

        return redirect("/notifications")

    @app.router.post("/notifications/api")
    @auth(roles=[ADMIN_ROLE])
    async def notifications_api_add(request: Request):
        """Add a notification from JSON: ``{"title", "text", "date"?}``.

        A notification with the same date and title is not duplicated; the
        existing one is returned with ``"created": false``.
        """
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            data = None

        if not isinstance(data, dict):
            return json_response({"error": "Expected a JSON object"}, status=400)

        title = str(data.get("title") or "").strip()
        text = str(data.get("text") or "")
        raw_date = data.get("date")
        date = str(raw_date).strip() if raw_date else None

        if not title:
            return json_response({"error": "title is required"}, status=400)

        try:
            notification_id, created = store.add_if_new(title, text, date)
            notification = store.get_by_id(notification_id)
        except Exception as e:  # noqa: BLE001
            await record_error(request, e, context={"title": title})
            return json_response({"error": "Could not store notification"}, status=500)

        assert notification is not None
        if created:
            _push(notification)
        return json_response(
            {"created": created, "notification": _serialize(notification)},
            status=201 if created else 200,
        )
