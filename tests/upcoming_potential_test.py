import pytest

from born_portal.upcoming.model import UpcomingData
from born_portal.upcoming.potential import (
    EventCluster,
    SourceEvent,
    cluster_events,
    normalize_name,
    rave_type,
)
from born_portal.upcoming.sources import Source


def _source(key: str, name: str) -> Source:
    async def fetch(start: str, end: str) -> list[UpcomingData]:
        return []

    return Source(key=key, name=name, url="https://example.com", fetch=fetch)


RA = _source("ra", "Ra.co")
RAVE = _source("raveoclock", "Ra.Clock")
TECHNO = _source("technoistockholm", "Techno Stockholm")


def _event(source: Source, name: str, date: str | None = None, url: str | None = None):
    return SourceEvent(
        source=source,
        event=UpcomingData(
            url=url or f"https://example.com/{source.key}",
            name=name,
            date=date,
        ),
    )


def test_rave_type_kept_but_ignored_for_normalization():
    name = "🔴 HARD | The Void — Hard Techno @ House of Q"
    assert rave_type(name) == "HARD"
    assert normalize_name(name) == "void hard techno house q"


def test_normalize_name_removes_filler_words():
    assert normalize_name("SHUTDOWN Gamla Stan (Gastronomics)") == (
        "shutdown gamla stan gastronomics"
    )
    assert normalize_name("Norman Methner at Neu") == "norman methner neu"


def test_cluster_groups_raveoclock_with_ra_and_keeps_type():
    events = [
        _event(RA, "SHUTDOWN Gamla Stan (Gastronomics)", "2026-11-06 23:00"),
        _event(
            RAVE,
            "🟢 SOCIAL | SHUTDOWN Gamla Stan @ Bistro Marie",
            "2026-11-06 23:00",
        ),
    ]
    clusters = cluster_events(events)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.primary.source is RAVE
    assert cluster.primary.event.name.startswith("🟢 SOCIAL")
    assert [alt.source for alt in cluster.alternatives] == [RA]


def test_cluster_matches_reordered_lineups():
    events = [
        _event(
            RA,
            "Jesper Dahlbäck, Alexi Delano & Nima Khak at Neu",
            "2026-11-07 23:59",
        ),
        _event(
            RAVE,
            "🔵 GROOVE | Alexi Delano · Jesper Dahlbäck · Nima Khak @ NEU",
            "2026-11-07 00:00",
        ),
    ]
    clusters = cluster_events(events)
    assert len(clusters) == 1
    assert len(clusters[0].alternatives) == 1


def test_cluster_merges_transitively():
    events = [
        _event(
            RA,
            "DEMAND Pres. WEHBBA | Molothav | DUAL DRIVE | Triara",
            "2026-11-07 22:00",
        ),
        _event(
            RAVE,
            "🔴 HARD | DEMAND — Wehbba @ Slakthuset",
            "2026-11-07 22:00",
        ),
        _event(
            TECHNO,
            "Wehbba (Brazil) I Dual Drive I Triara I Molothav",
            "2026-11-07 23:00",
        ),
    ]
    clusters = cluster_events(events)
    assert len(clusters) == 1
    assert len(clusters[0].alternatives) == 2


def test_cluster_keeps_different_events_apart():
    events = [
        _event(RA, "The Void - Hard Techno + BDSM play areas", "2026-11-07 21:00"),
        _event(RA, "Discovery Zone (Live)", "2026-11-08 17:00"),
    ]
    clusters = cluster_events(events)
    assert len(clusters) == 2


def test_cluster_does_not_merge_events_on_different_days():
    events = [
        _event(RA, "SHUTDOWN Gamla Stan", "2026-11-06 23:00"),
        _event(RA, "SHUTDOWN Gamla Stan", "2026-11-10 23:00"),
    ]
    clusters = cluster_events(events)
    assert len(clusters) == 2


def test_cluster_orders_by_date():
    events = [
        _event(RA, "Late Night", "2026-11-07 23:00"),
        _event(RA, "Early Evening", "2026-11-07 17:00"),
        _event(RA, "Friday Night", "2026-11-06 22:00"),
    ]
    clusters = cluster_events(events)
    assert [cluster.primary.event.name for cluster in clusters] == [
        "Friday Night",
        "Early Evening",
        "Late Night",
    ]


def test_cluster_uses_precise_date_from_alternative():
    events = [
        _event(RAVE, "🔵 GROOVE | Norman Methner @ NEU", "2026-11-06 - 2026-11-07"),
        _event(
            RA,
            "Norman Methner at Neu",
            "2026-11-06 23:59 - 2026-11-07 05:00",
        ),
    ]
    clusters = cluster_events(events)
    assert len(clusters) == 1
    assert clusters[0].date == "2026-11-06 23:59 - 2026-11-07 05:00"


def test_cluster_alternatives_are_rendered_with_primary():
    events = [
        _event(RA, "ASHR Label Night", "2026-11-07 22:00"),
        _event(RAVE, "🟣 DEEP | ASHR Label Night @ Under Bron", "2026-11-07 22:00"),
    ]
    clusters = cluster_events(events)
    assert len(clusters) == 1
    assert isinstance(clusters[0], EventCluster)
    assert clusters[0].primary.source is RAVE
    assert clusters[0].alternatives[0].source is RA


if __name__ == "__main__":
    pytest.main([__file__])
