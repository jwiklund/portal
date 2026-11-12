"""Tests for the SQLite-backed server-side session store."""

import asyncio
import time

from blacksheep import Request, Response
from blacksheep.cookies import CookieSameSiteMode
from blacksheep.sessions import Session
from itsdangerous import URLSafeTimedSerializer
from sqlmodel import Session as DbSession
from sqlmodel import SQLModel, create_engine, select

from born_portal.sessions import SessionRecord, SqliteSessionStore

_SECRET = "test-secret"
_COOKIE = "session"


def _make_store(tmp_path, *, max_age=3600, secure=False):
    engine = create_engine(f"sqlite:///{tmp_path / 'sessions.db'}")
    SQLModel.metadata.create_all(engine)
    store = SqliteSessionStore(engine, _SECRET, session_max_age=max_age, secure=secure)
    return store, engine


def _request(cookie_value=None, name=_COOKIE):
    headers = []
    if cookie_value is not None:
        headers.append((b"cookie", f"{name}={cookie_value}".encode()))
    return Request("GET", b"/", headers)


def _save(store, session, request=None):
    request = request or _request()
    response = Response(200)
    asyncio.run(store.save(request, response, session))
    return response


def _load(store, cookie_value):
    return asyncio.run(store.load(_request(cookie_value)))


def _rows(engine):
    with DbSession(engine) as db:
        return list(db.exec(select(SessionRecord)))


def test_save_then_load_round_trips(tmp_path):
    store, _ = _make_store(tmp_path)
    response = _save(store, Session({"user": "me@example.com"}))

    cookie = response.cookies[_COOKIE].value
    loaded = _load(store, cookie)

    assert loaded.get("user") == "me@example.com"


def test_cookie_does_not_reveal_payload(tmp_path):
    store, _ = _make_store(tmp_path)
    response = _save(
        store,
        Session({"user": "me@example.com", "spotify_refresh_token": "SECRET123"}),
    )

    cookie = response.cookies[_COOKIE].value
    assert "me@example.com" not in cookie
    assert "SECRET123" not in cookie


def test_no_cookie_loads_empty_session(tmp_path):
    store, _ = _make_store(tmp_path)
    assert _load(store, None).to_dict() == {}


def test_tampered_cookie_is_rejected(tmp_path):
    store, _ = _make_store(tmp_path)
    cookie = _save(store, Session({"user": "me@example.com"})).cookies[_COOKIE].value

    # Change the first payload character to every other base64url character.
    # That position carries significant bits, so each variant must fail
    # signature verification. (Flipping only the last character is unreliable:
    # its low bits can be insignificant in base64, so the tampered cookie can
    # decode to the exact same signed bytes and be accepted.)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    for replacement in alphabet:
        if replacement == cookie[0]:
            continue
        tampered = replacement + cookie[1:]
        assert _load(store, tampered).to_dict() == {}


def test_cookie_signed_with_other_secret_is_rejected(tmp_path):
    store, engine = _make_store(tmp_path)
    _save(store, Session({"user": "me@example.com"}))

    # Reuse the real, stored session id but sign it with a different secret,
    # as an attacker forging a cookie would.
    with DbSession(engine) as db:
        record = db.exec(select(SessionRecord)).first()
        assert record is not None
        forged = URLSafeTimedSerializer("different-secret").dumps(record.id)

    assert _load(store, forged).to_dict() == {}


def test_expired_record_drops_session(tmp_path):
    store, engine = _make_store(tmp_path)
    cookie = _save(store, Session({"user": "me@example.com"})).cookies[_COOKIE].value

    with DbSession(engine) as db:
        record = db.exec(select(SessionRecord)).first()
        assert record is not None
        row_id = record.id
        stored = db.get(SessionRecord, row_id)
        assert stored is not None
        stored.expires_at = time.time() - 1
        db.add(stored)
        db.commit()

    assert _load(store, cookie).to_dict() == {}
    assert _rows(engine) == []


def test_empty_session_clears_cookie_and_row(tmp_path):
    store, engine = _make_store(tmp_path)
    cookie = _save(store, Session({"user": "me@example.com"})).cookies[_COOKIE].value
    assert len(_rows(engine)) == 1

    response = _save(store, Session(), request=_request(cookie))

    assert _rows(engine) == []
    assert response.cookies[_COOKIE].max_age == 0


def test_cookie_security_attributes(tmp_path):
    store, _ = _make_store(tmp_path, secure=True)
    cookie = _save(store, Session({"user": "me@example.com"})).cookies[_COOKIE]

    assert cookie.http_only is True
    assert cookie.secure is True
    assert cookie.same_site == CookieSameSiteMode.LAX
    assert cookie.path == "/"
    assert cookie.max_age == 3600


def test_new_cookie_minted_per_modified_request(tmp_path):
    store, engine = _make_store(tmp_path)
    first = _save(store, Session({"oauth_state": "abc"})).cookies[_COOKIE].value
    second = (
        _save(store, Session({"oauth_state": "abc"}), request=_request(first))
        .cookies[_COOKIE]
        .value
    )

    # Reusing a valid id updates the existing row rather than creating another.
    assert first == second
    assert len(_rows(engine)) == 1
