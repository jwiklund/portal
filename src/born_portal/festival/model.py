from sqlmodel import Field, Relationship, SQLModel


class FestivalArtist(SQLModel, table=True):
    __tablename__ = "festival_artists"  # type: ignore[assignment]

    festival_id: int = Field(primary_key=True, foreign_key="festivals.id")
    artist_id: int = Field(primary_key=True, foreign_key="artists.id")
    position: int = Field(default=0)


class ArtistData(SQLModel, table=True):
    __tablename__ = "artists"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", unique=True, index=True)
    spotify_uri: str | None = None


class FestivalData(SQLModel, table=True):
    __tablename__ = "festivals"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    description: str = ""
    album_uri: str | None = None
    artists: list[ArtistData] = Relationship(
        link_model=FestivalArtist,
        sa_relationship_kwargs={
            "lazy": "selectin",
            "order_by": FestivalArtist.position,
        },
    )
