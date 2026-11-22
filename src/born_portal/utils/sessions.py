"""Server-side sessions backed by SQLite.

Only an opaque, signed session id travels in the browser cookie; the session
payload itself lives in the ``sessions`` table. This replaces the previous
signed-cookie store, where the whole payload -- including Spotify access and
refresh tokens -- was base64-encoded in the cookie. Signing protects against
modification but not disclosure, so anyone holding a copy of that cookie could
read the OAuth tokens. Keeping the data server-side fixes that: the cookie now
reveals nothing but a random identifier.
"""

from __future__ import annotations

import secrets
import time

from blacksheep.cookies import Cookie, CookieSameSiteMode
from blacksheep.messages import Request, Response
from blacksheep.sessions import Session, SessionStore
from blacksheep.sessions.json import JSONSerializer
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlmodel import Field, SQLModel, select
from sqlmodel import Session as DbSession


class SessionRecord(SQLModel, table=True):
    """One server-side session row.

    ``id`` is the random, signed value carried in the browser cookie; ``data``
    is the JSON-serialized session payload (user identity, OAuth state, Spotify
    tokens, ...).
    """

    __tablename__ = "sessions"  # type: ignore[assignment]

    id: str = Field(primary_key=True)
    data: str = ""
    # Unix timestamp after which the session is invalid; 0 means "no expiry".
    expires_at: float = 0.0


class SqliteSessionStore(SessionStore):
    """Persist sessions in SQLite, exposing only a signed session id.

    The session id is signed with ``secret_key`` so a client cannot forge or
    probe ids: an unsigned or tampered cookie is rejected before any database
    lookup. The signing also carries the session's max age, so expired cookies
    fail verification on their own.
    """

    def __init__(
        self,
        engine,
        secret_key: str,
        *,
        session_cookie: str = "session",
        session_max_age: int | None = None,
        secure: bool = False,
    ) -> None:
        if session_max_age is not None and session_max_age < 1:
            raise ValueError("session_max_age must be a positive number greater than 0")
        self._engine = engine
        self._signer = URLSafeTimedSerializer(secret_key)
        self._serializer = JSONSerializer()
        self._session_cookie = session_cookie
        self.session_max_age = session_max_age
        self._secure = secure

    async def load(self, request: Request) -> Session:
        session_id = self._read_session_id(request)
        if not session_id:
            return Session()

        with DbSession(self._engine) as db:
            record = db.get(SessionRecord, session_id)
            if record is None:
                return Session()
            if _is_expired(record):
                db.delete(record)
                db.commit()
                return Session()
            return self._serializer.read(record.data)

    async def save(
        self, request: Request, response: Response, session: Session
    ) -> None:
        session_id = self._read_session_id(request)
        data = session.to_dict()

        # An emptied session (e.g. logout) drops the row and clears the cookie
        # rather than leaving an empty record behind.
        if not data:
            if session_id:
                with DbSession(self._engine) as db:
                    record = db.get(SessionRecord, session_id)
                    if record is not None:
                        db.delete(record)
                        db.commit()
            self._clear_cookie(response)
            return

        now = time.time()
        expires_at = now + self.session_max_age if self.session_max_age else 0.0
        payload = self._serializer.write(session)

        with DbSession(self._engine) as db:
            _delete_expired(db, now)
            record = db.get(SessionRecord, session_id) if session_id else None
            if record is None:
                # No server-side session yet: mint a fresh, unguessable id so a
                # stale or deleted id is never resurrected.
                session_id = secrets.token_urlsafe(32)
                record = SessionRecord(
                    id=session_id, data=payload, expires_at=expires_at
                )
            else:
                record.data = payload
                record.expires_at = expires_at
            db.add(record)
            db.commit()

        response.set_cookie(self._prepare_cookie(self._signer.dumps(session_id)))

    def _read_session_id(self, request: Request) -> str | None:
        raw = request.cookies.get(self._session_cookie)
        if not raw:
            return None
        try:
            if self.session_max_age:
                value = self._signer.loads(raw, max_age=self.session_max_age)
            else:
                value = self._signer.loads(raw)
        except (BadSignature, SignatureExpired):
            return None
        return value if isinstance(value, str) and value else None

    def _prepare_cookie(self, value: str) -> Cookie:
        cookie = Cookie(
            self._session_cookie,
            value,
            path="/",
            http_only=True,
            max_age=self.session_max_age or -1,
        )
        cookie.secure = self._secure
        cookie.same_site = CookieSameSiteMode.LAX
        return cookie

    def _clear_cookie(self, response: Response) -> None:
        cookie = Cookie(self._session_cookie, "", path="/", http_only=True, max_age=0)
        cookie.secure = self._secure
        cookie.same_site = CookieSameSiteMode.LAX
        response.set_cookie(cookie)


def _is_expired(record: SessionRecord) -> bool:
    return bool(record.expires_at) and record.expires_at < time.time()


def _delete_expired(db: DbSession, now: float) -> None:
    """Remove rows whose expiry has passed (best-effort housekeeping)."""
    expired = db.exec(
        select(SessionRecord).where(
            SessionRecord.expires_at != 0, SessionRecord.expires_at < now
        )
    ).all()
    for record in expired:
        db.delete(record)
