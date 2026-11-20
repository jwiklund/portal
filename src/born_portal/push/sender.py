"""Deliver web-push notifications to stored browser subscriptions.

A delivery failure never breaks the request that created the notification: the
error is recorded in the error log instead (see ``errors``). Subscriptions the
push service reports as gone (HTTP 404/410) are deleted.
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlsplit

from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from born_portal.core import ADMIN_USERS, VAPID_SUBJECT
from born_portal.errors import record_error
from born_portal.push.keys import VapidNotConfigured, load_vapid_instance
from born_portal.push.model import PushSubscription
from born_portal.push.store import PushSubscriptionStore

logger = logging.getLogger(__name__)

# HTTP statuses meaning the subscription no longer exists and can be dropped.
_GONE_STATUS = {404, 410}
# How long the push service should retain a message for an offline device.
_TTL_SECONDS = 24 * 3600
# Abort a delivery that the push service does not answer within this many seconds.
_TIMEOUT_SECONDS = 10

_store: PushSubscriptionStore | None = None

# Strong references to in-flight delivery tasks. asyncio only keeps a weak
# reference to tasks, so without this a fire-and-forget send could be
# garbage-collected before it finishes.
_tasks: set[asyncio.Task] = set()


def configure(engine) -> None:
    """Point the sender at the database that holds the subscriptions."""
    global _store
    _store = PushSubscriptionStore(engine)


def _subject() -> str:
    """The VAPID "sub" claim: a contact URI for the push service."""
    if VAPID_SUBJECT:
        return VAPID_SUBJECT
    contact = next(iter(sorted(ADMIN_USERS)), None)
    return f"mailto:{contact}" if contact else "mailto:admin@localhost"


def _endpoint_host(endpoint: str) -> str:
    """A non-secret label for an endpoint, safe to store in the error log."""
    try:
        return urlsplit(endpoint).netloc or endpoint[:32]
    except Exception:  # noqa: BLE001
        return endpoint[:32]


def _payload(notification) -> str:
    return json.dumps(
        {
            "title": notification.title,
            "body": notification.text,
            "url": "/notifications",
        },
        ensure_ascii=False,
    )


def _deliver(subscription: PushSubscription, payload: str, vapid: Vapid) -> None:
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=payload,
        vapid_private_key=vapid,
        vapid_claims={"sub": _subject()},
        ttl=_TTL_SECONDS,
        timeout=_TIMEOUT_SECONDS,
    )


async def send_notification(notification) -> None:
    """Push ``notification`` to every stored subscription.

    Never raises: failures are recorded in the error log, and subscriptions the
    push service rejects as gone are deleted.
    """
    if _store is None:
        return

    subscriptions = _store.all()
    if not subscriptions:
        return

    try:
        vapid = load_vapid_instance()
    except VapidNotConfigured:
        # Push is disabled until VAPID keys are configured; not an error.
        return
    except Exception as e:  # noqa: BLE001
        await record_error(None, e, context={"stage": "push_vapid"})
        return

    payload = _payload(notification)

    for subscription in subscriptions:
        context = {
            "stage": "push_delivery",
            "endpoint": _endpoint_host(subscription.endpoint),
            "notification_id": notification.id,
        }
        try:
            await asyncio.to_thread(_deliver, subscription, payload, vapid)
        except WebPushException as e:
            await record_error(None, e, context={**context, "status": e.status_code})
            if e.status_code in _GONE_STATUS:
                _store.delete_by_endpoint(subscription.endpoint)
        except Exception as e:  # noqa: BLE001
            await record_error(None, e, context=context)


def schedule_notification(notification) -> None:
    """Deliver ``notification`` in the background.

    Called from request handlers so the save/redirect/response is not blocked
    by slow push-service calls. ``send_notification`` already records failures
    and swallows exceptions; the done-callback just logs anything that still
    escapes.
    """
    task = asyncio.create_task(send_notification(notification))
    _tasks.add(task)
    task.add_done_callback(_on_task_done)


def _on_task_done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("Push delivery task failed", exc_info=task.exception())
