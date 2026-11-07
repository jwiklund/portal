from __future__ import annotations

from sqlalchemy import Engine
from sqlmodel import Session, select

from born_portal.past.model import ArtistData, PastArtist, PastData


class PastStore:
    """SQLite storage for past events and their artists."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def save(self, past: PastData) -> int:
        """Save a past event with its artist list. Returns the row id."""
        with Session(self._engine) as session:
            if past.id:
                existing = session.get(PastData, past.id)
                if existing is not None:
                    self._copy_fields(existing, past)
                    session.add(existing)
                    past_id = past.id
                else:
                    past_id = self._insert_past(session, past)
            else:
                past_id = self._insert_past(session, past)

            assert past_id is not None

            # Replace the artist list
            self._replace_artists(session, past_id, past.artists)
            session.commit()
            return past_id

    @staticmethod
    def _copy_fields(target: PastData, source: PastData) -> None:
        target.name = source.name
        target.start_date = source.start_date
        target.end_date = source.end_date
        target.location = source.location
        target.description = source.description
        target.album_uri = source.album_uri

    @staticmethod
    def _insert_past(session: Session, past: PastData) -> int:
        # Build a fresh row without the relationship collection so no
        # transient artists are cascade-inserted from the caller's object.
        row = PastData(
            name=past.name,
            start_date=past.start_date,
            end_date=past.end_date,
            location=past.location,
            description=past.description,
            album_uri=past.album_uri,
        )
        session.add(row)
        session.flush()
        assert row.id is not None
        return row.id

    @staticmethod
    def _replace_artists(
        session: Session,
        past_id: int,
        artists: list[ArtistData],
    ) -> None:
        links = session.exec(
            select(PastArtist).where(PastArtist.past_id == past_id)
        ).all()
        for link in links:
            session.delete(link)
        for position, artist in enumerate(artists):
            if not artist.name.strip():
                continue
            artist_id = PastStore._upsert_artist(session, artist)
            session.add(
                PastArtist(
                    past_id=past_id,
                    artist_id=artist_id,
                    position=position,
                )
            )

    @staticmethod
    def _upsert_artist(session: Session, artist: ArtistData) -> int:
        existing = session.exec(
            select(ArtistData).where(ArtistData.name == artist.name.strip())
        ).first()
        if existing is not None:
            existing.spotify_uri = artist.spotify_uri
            session.add(existing)
            assert existing.id is not None
            return existing.id
        row = ArtistData(name=artist.name.strip(), spotify_uri=artist.spotify_uri)
        session.add(row)
        session.flush()
        assert row.id is not None
        return row.id

    def get_by_id(self, id: int) -> PastData | None:
        with Session(self._engine) as session:
            return session.get(PastData, id)

    def list_all(self) -> list[PastData]:
        with Session(self._engine) as session:
            items = list(session.exec(select(PastData)))
        items.sort(key=lambda f: f.start_date or "", reverse=True)
        return items

    def known_album_uris(self) -> list[str]:
        with Session(self._engine) as session:
            uris = session.exec(
                select(PastData.album_uri).where(
                    PastData.album_uri != None,
                    PastData.album_uri != "",
                )
            )
        return list(dict.fromkeys(uri for uri in uris if uri))

    def delete(self, id: int) -> bool:
        with Session(self._engine) as session:
            past = session.get(PastData, id)
            if past is None:
                return False
            session.delete(past)
            session.commit()
            return True
