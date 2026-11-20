import asyncio
import json
from pathlib import Path

import pytest
from py_vapid import Vapid
from sqlmodel import SQLModel, create_engine

from born_portal.errors import configure as configure_errors
from born_portal.errors.store import ErrorStore
from born_portal.notifications.model import Notification
from born_portal.push import keys, sender
from born_portal.push.model import PushSubscription
from born_portal.push.store import PushSubscriptionStore


def make_store(tmp_path) -> tuple[PushSubscriptionStore, object]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return PushSubscriptionStore(engine), engine


def test_save_upserts_by_endpoint(tmp_path):
    store, _ = make_store(tmp_path)
    first_id = store.save(
        PushSubscription(endpoint="https://push/1", p256dh="a", auth="b", user="u@x")
    )
    second_id = store.save(
        PushSubscription(endpoint="https://push/1", p256dh="c", auth="d", user="v@x")
    )

    assert first_id == second_id
    assert store.count() == 1
    saved = store.all()[0]
    assert saved.p256dh == "c"
    assert saved.auth == "d"
    assert saved.user == "v@x"


def test_delete_by_endpoint(tmp_path):
    store, _ = make_store(tmp_path)
    store.save(PushSubscription(endpoint="https://push/1", p256dh="a", auth="b"))
    store.save(PushSubscription(endpoint="https://push/2", p256dh="a", auth="b"))

    assert store.count() == 2
    assert store.delete_by_endpoint("https://push/1") is True
    assert store.count() == 1
    assert store.delete_by_endpoint("https://push/1") is False


def test_generate_returns_usable_pair():
    public_key, private_key = keys.generate()

    assert public_key and "=" not in public_key
    assert private_key.startswith("-----BEGIN")


def test_load_vapid_prefers_env(monkeypatch):
    monkeypatch.setattr(keys, "VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setattr(keys, "VAPID_PRIVATE_KEY", "priv")

    assert keys.load_vapid() == ("pub", "priv")


def test_load_vapid_raises_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setattr(keys, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(keys, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(keys, "VAPID_KEY_FILE", tmp_path / "missing.json")

    assert keys.vapid_configured() is False
    with pytest.raises(keys.VapidNotConfigured):
        keys.load_vapid()


def test_load_vapid_reads_key_file(monkeypatch, tmp_path):
    public_key, private_key = keys.generate()
    key_file = tmp_path / "vapid_keys.json"
    key_file.write_text(
        json.dumps({"public_key": public_key, "private_key": private_key})
    )
    monkeypatch.setattr(keys, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(keys, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(keys, "VAPID_KEY_FILE", key_file)

    assert keys.vapid_configured() is True
    assert keys.load_vapid() == (public_key, private_key)


def test_load_vapid_instance_parses_pem(monkeypatch):
    public_key, private_key = keys.generate()
    monkeypatch.setattr(keys, "VAPID_PUBLIC_KEY", public_key)
    monkeypatch.setattr(keys, "VAPID_PRIVATE_KEY", private_key)

    instance = keys.load_vapid_instance()

    assert isinstance(instance, Vapid)
    # The instance corresponds to the pair the browser subscribed with.
    assert keys._public_key_b64(instance) == public_key


def test_systemd_private_key_escapes_newlines():
    _, private_key = keys.generate()
    assert "\n" in private_key

    escaped = keys.systemd_private_key(private_key)

    assert "\n" not in escaped
    assert "\\n" in escaped
    # systemd turns the \n escapes back into newlines; a PEM has no %/\/" so
    # the only transformation is the newline escaping.
    assert escaped.replace("\\n", "\n") == private_key.strip()


def test_systemd_private_key_doubles_percent():
    # % is a systemd specifier, so a literal one must be doubled.
    assert keys.systemd_private_key("a%b") == "a%%b"


def test_schedule_notification_runs_in_background(monkeypatch):
    delivered = []

    async def fake_send(notification):
        delivered.append(notification.id)

    monkeypatch.setattr(sender, "send_notification", fake_send)

    async def go():
        sender.schedule_notification(Notification(id=7, title="T", text="B"))
        # Drain the scheduled task(s) without awaiting in the request path.
        while sender._tasks:
            await asyncio.sleep(0)

    asyncio.run(go())

    assert delivered == [7]
    assert sender._tasks == set()


class _GoneResponse:
    status_code = 410
    text = "Gone"


def test_delivery_passes_vapid_instance_and_records_gone(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    store = PushSubscriptionStore(engine)
    store.save(PushSubscription(endpoint="https://push/1", p256dh="a", auth="b"))

    sender.configure(engine)
    configure_errors(engine)

    # Use a real (PEM) key pair so the production conversion path runs.
    public_key, private_key = keys.generate()
    monkeypatch.setattr(keys, "VAPID_PUBLIC_KEY", public_key)
    monkeypatch.setattr(keys, "VAPID_PRIVATE_KEY", private_key)

    captured = {}

    def boom(*args, **kwargs):
        captured.update(kwargs)
        raise sender.WebPushException("gone", response=_GoneResponse())

    monkeypatch.setattr(sender, "webpush", boom)

    asyncio.run(sender.send_notification(Notification(id=1, title="T", text="B")))

    # The PEM key must be converted to a Vapid instance before it reaches
    # pywebpush (a raw PEM string makes pywebpush raise ValueError).
    assert isinstance(captured["vapid_private_key"], Vapid)
    assert captured["subscription_info"]["endpoint"] == "https://push/1"

    # The gone subscription is dropped and the failure is in the error log.
    assert store.count() == 0
    errors = ErrorStore(engine).list_recent()
    assert len(errors) == 1
    assert errors[0].exception_type == "WebPushException"
    assert "push_delivery" in errors[0].context
    assert '"endpoint": "push"' in errors[0].context


def test_subscriber_count(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    store = PushSubscriptionStore(engine)
    sender.configure(engine)

    assert sender.subscriber_count() == 0
    store.save(PushSubscription(endpoint="https://push/1", p256dh="a", auth="b"))
    assert sender.subscriber_count() == 1


def test_send_notification_returns_delivered_count(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    store = PushSubscriptionStore(engine)
    store.save(PushSubscription(endpoint="https://push/1", p256dh="a", auth="b"))
    store.save(PushSubscription(endpoint="https://push/2", p256dh="a", auth="b"))

    sender.configure(engine)
    configure_errors(engine)

    public_key, private_key = keys.generate()
    monkeypatch.setattr(keys, "VAPID_PUBLIC_KEY", public_key)
    monkeypatch.setattr(keys, "VAPID_PRIVATE_KEY", private_key)
    monkeypatch.setattr(sender, "webpush", lambda **kwargs: None)

    delivered = asyncio.run(
        sender.send_notification(Notification(id=1, title="T", text="B"))
    )

    assert delivered == 2


def test_send_notification_returns_zero_when_unconfigured(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    PushSubscriptionStore(engine).save(
        PushSubscription(endpoint="https://push/1", p256dh="a", auth="b")
    )
    sender.configure(engine)

    monkeypatch.setattr(keys, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(keys, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(keys, "VAPID_KEY_FILE", tmp_path / "missing.json")

    delivered = asyncio.run(
        sender.send_notification(Notification(id=1, title="T", text="B"))
    )

    assert delivered == 0


def test_notifications_page_reloads_on_push():
    from born_portal.core import jinja, render
    from born_portal.notifications.routes import linkify

    jinja.filters["linkify"] = linkify
    body = render(
        "notifications.html",
        None,
        notifications=[],
        new_ids=set(),
        new_count=0,
        push_configured=False,
        is_admin=True,
        user=None,
    ).content.body.decode()

    # The page listens for the service worker's push message and reloads.
    assert "portal-push" in body
    assert "serviceWorker.addEventListener" in body


def test_service_worker_notifies_open_clients():
    sw = (Path(sender.__file__).parent / "sw.js").read_text()

    assert 'client.postMessage({ type: "portal-push"' in sw
