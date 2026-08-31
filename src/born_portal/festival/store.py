from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

from born_portal.festival.model import ArtistData, FestivalArtist, FestivalData


class FestivalStore:
    """SQLite storage for festivals and their artists."""

    def __init__(self, db_path: str = "events.db"):
        self._engine = create_engine(f"sqlite:///{db_path}")
        SQLModel.metadata.create_all(self._engine)

    def close(self) -> None:
        self._engine.dispose()

    def save(self, festival: FestivalData) -> int:
        """Save a festival with its artist list. Returns the row id."""
        with Session(self._engine) as session:
            if festival.id:
                existing = session.get(FestivalData, festival.id)
                if existing is not None:
                    self._copy_fields(existing, festival)
                    session.add(existing)
                    festival_id = festival.id
                else:
                    festival_id = self._insert_festival(session, festival)
            else:
                festival_id = self._insert_festival(session, festival)

            assert festival_id is not None

            # Replace the artist list
            self._replace_artists(session, festival_id, festival.artists)
            session.commit()
            return festival_id

    @staticmethod
    def _copy_fields(target: FestivalData, source: FestivalData) -> None:
        target.name = source.name
        target.start_date = source.start_date
        target.end_date = source.end_date
        target.location = source.location
        target.description = source.description
        target.album_uri = source.album_uri

    @staticmethod
    def _insert_festival(session: Session, festival: FestivalData) -> int:
        # Build a fresh row without the relationship collection so no
        # transient artists are cascade-inserted from the caller's object.
        row = FestivalData(
            name=festival.name,
            start_date=festival.start_date,
            end_date=festival.end_date,
            location=festival.location,
            description=festival.description,
            album_uri=festival.album_uri,
        )
        session.add(row)
        session.flush()
        assert row.id is not None
        return row.id

    @staticmethod
    def _replace_artists(
        session: Session,
        festival_id: int,
        artists: list[ArtistData],
    ) -> None:
        links = session.exec(
            select(FestivalArtist).where(FestivalArtist.festival_id == festival_id)
        ).all()
        for link in links:
            session.delete(link)
        for position, artist in enumerate(artists):
            if not artist.name.strip():
                continue
            artist_id = FestivalStore._upsert_artist(session, artist)
            session.add(
                FestivalArtist(
                    festival_id=festival_id,
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

    def get_by_id(self, id: int) -> FestivalData | None:
        with Session(self._engine) as session:
            return session.get(FestivalData, id)

    def list_all(self) -> list[FestivalData]:
        with Session(self._engine) as session:
            festivals = list(session.exec(select(FestivalData)))
        festivals.sort(key=lambda f: f.start_date or "", reverse=True)
        return festivals

    def known_album_uris(self) -> list[str]:
        with Session(self._engine) as session:
            uris = session.exec(
                select(FestivalData.album_uri).where(
                    FestivalData.album_uri != None,
                    FestivalData.album_uri != "",
                )
            )
        return list(dict.fromkeys(uri for uri in uris if uri))

    def delete(self, id: int) -> bool:
        with Session(self._engine) as session:
            festival = session.get(FestivalData, id)
            if festival is None:
                return False
            session.delete(festival)
            session.commit()
            return True
