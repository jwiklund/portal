"""Web-push subscription endpoints and the service worker script."""

from __future__ import annotations

from pathlib import Path

import aiofiles
from blacksheep import Request, Response
from blacksheep.contents import Content
from blacksheep.server.responses import json

from born_portal.auth.guard import allow_anonymous, auth
from born_portal.push.keys import VapidNotConfigured, load_vapid
from born_portal.push.model import PushSubscription
from born_portal.push.sender import configure
from born_portal.push.store import PushSubscriptionStore

HERE = Path(__file__).parent


def register_routes(app, engine):
    store = PushSubscriptionStore(engine)
    configure(engine)

    @app.router.get("/sw.js")
    @allow_anonymous()
    async def service_worker(request: Request):
        async with aiofiles.open(HERE / "sw.js", "rb") as f:
            response = Response(
                200, content=Content(b"application/javascript", await f.read())
            )
        # Service workers are cached aggressively by browsers; force
        # revalidation so an updated worker takes effect promptly.
        response.set_header(b"Cache-Control", b"no-cache")
        return response

    @app.router.get("/push/vapid")
    @auth()
    async def push_vapid(request: Request):
        try:
            public_key, _ = load_vapid()
        except VapidNotConfigured:
            return json({"error": "Push notifications are not configured"}, status=503)
        return json({"publicKey": public_key})

    @app.router.post("/push/subscribe")
    @auth()
    async def push_subscribe(request: Request):
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            data = None
        if not isinstance(data, dict):
            return json({"error": "Expected a JSON object"}, status=400)

        endpoint = str(data.get("endpoint") or "").strip()
        keys = data.get("keys") or {}
        p256dh = str(keys.get("p256dh") or "")
        auth_key = str(keys.get("auth") or "")
        if not endpoint or not p256dh or not auth_key:
            return json({"error": "Missing subscription fields"}, status=400)

        header = request.get_first_header(b"user-agent")
        store.save(
            PushSubscription(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth_key,
                user=request.session.get("user"),
                user_agent=header.decode("utf-8", "replace") if header else None,
            )
        )
        return json({"ok": True})

    @app.router.post("/push/unsubscribe")
    @auth()
    async def push_unsubscribe(request: Request):
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            data = None
        endpoint = str((data or {}).get("endpoint") or "").strip()
        if endpoint:
            store.delete_by_endpoint(endpoint)
        return json({"ok": True})
