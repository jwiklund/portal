from sqlmodel import SQLModel, Session, create_engine, func, select

from born_portal.festival.model import ArtistData, FestivalData
from born_portal.festival.store import FestivalStore


def make_store(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return FestivalStore(engine)


def artist_count(store) -> int:
    with Session(store._engine) as conn:
        query = select(func.count()).select_from(ArtistData)
        return conn.exec(query).one()


def test_save_and_get_roundtrip(tmp_path):
    store = make_store(tmp_path)
    festival_id = store.save(
        FestivalData(
            name="Way Out West",
            start_date="2026-08-12",
            end_date="2026-08-14",
            location="Gothenburg",
            description="A festival.",
            album_uri="https://photos.google.com/share/abc?key=def",
            artists=[
                ArtistData(name="Artist One", spotify_uri="spotify:artist:1"),
                ArtistData(name="Artist Two"),
            ],
        )
    )

    loaded = store.get_by_id(festival_id)
    assert loaded is not None
    assert loaded.name == "Way Out West"
    assert loaded.start_date == "2026-08-12"
    assert loaded.end_date == "2026-08-14"
    assert loaded.location == "Gothenburg"
    assert loaded.album_uri == "https://photos.google.com/share/abc?key=def"
    assert [a.name for a in loaded.artists] == ["Artist One", "Artist Two"]
    assert loaded.artists[0].spotify_uri == "spotify:artist:1"
    assert loaded.artists[1].spotify_uri is None


def test_update_preserves_id_and_replaces_artists(tmp_path):
    store = make_store(tmp_path)
    festival_id = store.save(
        FestivalData(
            name="Original",
            artists=[ArtistData(name="A"), ArtistData(name="B")],
        )
    )
    store.save(
        FestivalData(
            id=festival_id,
            name="Updated",
            start_date="2027-01-01",
            artists=[ArtistData(name="C", spotify_uri="spotify:artist:3")],
        )
    )

    loaded = store.get_by_id(festival_id)
    assert loaded is not None
    assert loaded.name == "Updated"
    assert loaded.start_date == "2027-01-01"
    assert [a.name for a in loaded.artists] == ["C"]


def test_artist_deduplicated_across_festivals(tmp_path):
    store = make_store(tmp_path)
    store.save(FestivalData(name="F1", artists=[ArtistData(name="Shared")]))
    store.save(FestivalData(name="F2", artists=[ArtistData(name="Shared")]))

    assert artist_count(store) == 1


def test_relinking_existing_artists_keeps_correct_ids(tmp_path):
    store = make_store(tmp_path)
    f1 = store.save(
        FestivalData(
            name="F1", artists=[ArtistData(name="A"), ArtistData(name="B")]
        )
    )
    f2 = store.save(FestivalData(name="F2", artists=[ArtistData(name="C")]))

    store.save(
        FestivalData(
            id=f1,
            name="F1",
            artists=[ArtistData(name="A"), ArtistData(name="B")],
        )
    )
    loaded = store.get_by_id(f1)
    assert loaded is not None
    assert [a.name for a in loaded.artists] == ["A", "B"]

    loaded = store.get_by_id(f2)
    assert loaded is not None
    assert [a.name for a in loaded.artists] == ["C"]

    assert artist_count(store) == 3


def test_list_all_orders_by_start_date_desc(tmp_path):
    store = make_store(tmp_path)
    store.save(FestivalData(name="Newest", start_date="2026-08-12"))
    store.save(FestivalData(name="Oldest", start_date="2024-07-01"))
    store.save(FestivalData(name="No Date"))

    names = [f.name for f in store.list_all()]
    assert names == ["Newest", "Oldest", "No Date"]


def test_known_album_uris(tmp_path):
    store = make_store(tmp_path)
    store.save(
        FestivalData(name="A", album_uri="https://photos.google.com/share/x")
    )
    store.save(
        FestivalData(name="B", album_uri="https://photos.google.com/share/x")
    )
    store.save(FestivalData(name="C"))

    assert store.known_album_uris() == ["https://photos.google.com/share/x"]


def test_delete_removes_festival_and_links(tmp_path):
    store = make_store(tmp_path)
    festival_id = store.save(
        FestivalData(name="Doomed", artists=[ArtistData(name="A")])
    )
    assert store.delete(festival_id) is True
    assert store.get_by_id(festival_id) is None
    assert store.list_all() == []


def test_blank_artist_names_skipped(tmp_path):
    store = make_store(tmp_path)
    festival_id = store.save(
        FestivalData(
            name="F", artists=[ArtistData(name="  "), ArtistData(name="Real")]
        )
    )
    loaded = store.get_by_id(festival_id)
    assert loaded is not None
    assert [a.name for a in loaded.artists] == ["Real"]