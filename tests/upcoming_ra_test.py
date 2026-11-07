import pytest

from born_portal.upcoming.sources.ra import parse_events


def _payload(*listings):
    return {"data": {"eventListings": {"data": list(listings)}}}


def test_parse_full_event():
    payload = _payload(
        {
            "id": "2563067",
            "event": {
                "title": "Uteklubben",
                "date": "2026-11-13",
                "startTime": "2026-11-13T22:00:00.000",
                "endTime": "2026-11-14T05:00:00.000",
                "contentUrl": "/events/2563067",
                "cost": "150 kr",
                "isTicketed": True,
                "content": "<p>All&nbsp;night</p><p>House &amp; techno</p>",
                "venue": {"name": "Slakthuset"},
            },
        }
    )

    events = parse_events(payload)

    assert len(events) == 1
    event = events[0]
    assert event.url == "https://ra.co/events/2563067"
    assert event.name == "Uteklubben"
    assert event.location == "Slakthuset"
    assert event.price == "150 kr"
    assert event.ticket is True
    assert event.date == "2026-11-13 22:00 - 2026-11-14 05:00"
    assert event.description == "All night House & techno"


def test_parse_empty_cost_becomes_none():
    payload = _payload(
        {
            "id": "1",
            "event": {
                "title": "Free party",
                "startTime": "2026-11-14T20:00:00.000",
                "endTime": "2026-11-15T01:00:00.000",
                "contentUrl": "/events/1",
                "cost": "",
                "isTicketed": False,
                "content": "",
                "venue": {"name": "TBA"},
            },
        }
    )

    event = parse_events(payload)[0]

    assert event.price is None
    assert event.ticket is False
    assert event.location == "TBA"
    assert event.date == "2026-11-14 20:00 - 2026-11-15 01:00"
    assert event.description == ""


def test_parse_missing_end_time():
    payload = _payload(
        {
            "id": "2",
            "event": {
                "title": "Single",
                "startTime": "2026-11-13T22:00:00.000",
                "endTime": None,
                "contentUrl": "/events/2",
                "venue": None,
            },
        }
    )

    event = parse_events(payload)[0]

    assert event.date == "2026-11-13 22:00"
    assert event.location is None


def test_parse_skips_entries_without_event_or_url():
    payload = _payload(
        {"id": "3", "event": None},
        {"id": "4", "event": {"title": "No URL"}},
        {
            "id": "5",
            "event": {
                "title": "Good",
                "startTime": "2026-11-13T22:00:00.000",
                "contentUrl": "/events/5",
            },
        },
    )

    events = parse_events(payload)

    assert [event.url for event in events] == ["https://ra.co/events/5"]


def test_parse_empty_payload():
    assert parse_events({}) == []


if __name__ == "__main__":
    pytest.main([__file__])
