from __future__ import annotations

from sqlalchemy import Engine, func
from sqlmodel import Session, select

from born_portal.push.model import PushSubscription


class PushSubscriptionStore:
    """SQLite storage for browser push subscriptions."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def save(self, subscription: PushSubscription) -> int:
        """Insert a subscription, or refresh the keys of an existing endpoint."""
        with Session(self._engine) as session:
            existing = session.exec(
                select(PushSubscription).where(
                    PushSubscription.endpoint == subscription.endpoint
                )
            ).first()
            if existing is not None:
                existing.p256dh = subscription.p256dh
                existing.auth = subscription.auth
                existing.user = subscription.user
                existing.user_agent = subscription.user_agent
                session.add(existing)
                session.commit()
                assert existing.id is not None
                return existing.id

            session.add(subscription)
            session.commit()
            session.refresh(subscription)
            assert subscription.id is not None
            return subscription.id

    def all(self) -> list[PushSubscription]:
        with Session(self._engine) as session:
            return list(session.exec(select(PushSubscription)))

    def count(self) -> int:
        with Session(self._engine) as session:
            return session.exec(
                select(func.count()).select_from(PushSubscription)
            ).one()

    def delete_by_endpoint(self, endpoint: str) -> bool:
        with Session(self._engine) as session:
            row = session.exec(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
