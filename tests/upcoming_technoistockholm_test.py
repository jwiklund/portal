import json

import pytest

from born_portal.upcoming.sources.technoistockholm import (
    extract_events,
    parse_events,
)


def _row(**overrides):
    row = {
        "startDate": "2026-11-27T22:00:00.000Z",
        "slug": "warehouse-night",
        "title": "Warehouse Night",
        "description": "A night of techno.\nDoors 22:00.",
        "venues": [
            {"name": "Uppsala, Uppsala", "address": "Uppsala", "city": "Uppsala"}
        ],
        "tickets": [
            {
                "url": "https://billetto.se/e/1",
                "type": "general admission",
                "price": "80",
            }
        ],
        "url": None,
    }
    row.update(overrides)
    return row


def test_parse_events_in_range():
    # 2026-11-27T22:00Z is 23:00 local (CET, UTC+1).
    events = parse_events([_row()], "2026-11-27", "2026-11-29")
    assert len(events) == 1
    event = events[0]
    assert event.url == "https://billetto.se/e/1"
    assert event.name == "Warehouse Night"
    assert event.description == "A night of techno.\nDoors 22:00."
    assert event.location == "Uppsala, Uppsala"
    assert event.price == "80"
    assert event.date == "2026-11-27 23:00"
    assert event.ticket is True


def test_parse_events_out_of_range():
    events = parse_events([_row()], "2026-11-06", "2026-11-08")
    assert events == []


def test_parse_events_no_venues_or_tickets():
    row = _row(venues=[], tickets=[])
    events = parse_events([row], "2026-11-27", "2026-11-29")
    assert len(events) == 1
    assert events[0].url == "https://technoistockholm.se/events/warehouse-night"
    assert events[0].location is None
    assert events[0].price is None
    assert events[0].ticket is False


def test_parse_events_falls_back_when_ticket_url_is_duplicate():
    row = _row(tickets=[{"url": "https://billetto.se/e/1", "price": "80"}])
    events = parse_events([row, row], "2026-11-27", "2026-11-29")
    assert len(events) == 2
    assert events[0].url == "https://billetto.se/e/1"
    assert events[1].url == "https://technoistockholm.se/events/warehouse-night"


def test_parse_events_skips_malformed_ticket_url():
    row = _row(
        tickets=[
            {
                "url": "https://billetto.sehttps://billetto.se/e/1",
                "price": "80",
            },
            {"url": "https://billetto.se/e/2", "price": "80"},
        ]
    )
    events = parse_events([row], "2026-11-27", "2026-11-29")
    assert events[0].url == "https://billetto.se/e/2"


def test_parse_events_location_falls_back_to_address():
    row = _row(venues=[{"name": None, "address": "Sveavägen 1", "city": "Stockholm"}])
    events = parse_events([row], "2026-11-27", "2026-11-29")
    assert events[0].location == "Sveavägen 1, Stockholm"


def test_parse_events_price_skips_empty_ticket_price():
    row = _row(
        tickets=[
            {"url": "https://billetto.se/e/1", "type": None, "price": None},
            {"url": "https://billetto.se/e/2", "type": "vip", "price": "150"},
        ]
    )
    events = parse_events([row], "2026-11-27", "2026-11-29")
    assert events[0].price == "150"
    assert events[0].ticket is True


def test_parse_events_date_boundary_is_local():
    # 2026-11-27T22:30Z is 23:30 local on the 27th, so it is in range ...
    assert parse_events(
        [_row(startDate="2026-11-27T22:30:00.000Z")], "2026-11-27", "2026-11-27"
    )
    # ... while 2026-11-27T23:30Z is 00:30 local on the 28th, so it is not.
    assert (
        parse_events(
            [_row(startDate="2026-11-27T23:30:00.000Z")], "2026-11-27", "2026-11-27"
        )
        == []
    )


def test_extract_events_from_rsc_stream():
    payload = {
        "events": [
            {
                "startDate": "2026-11-14T22:00:00.000Z",
                "slug": "opening-party",
                "title": "Opening [Party]",
                "description": "With {braces} and ]brackets[ inside",
                "venues": [{"name": "Stockholm"}],
                "tickets": [{"url": "https://billetto.se/e/2", "price": "100"}],
                "url": None,
            }
        ]
    }
    inner = json.dumps(payload, separators=(",", ":"))
    # A Next.js RSC push wraps the inner JSON as an escaped JSON string.
    chunk = json.dumps(inner)
    html = f"<script>self.__next_f.push([1,{chunk}])</script>"
    assert extract_events(html) == payload["events"]


def test_extract_events_concatenates_chunks():
    first = json.dumps('{"events":[{"slug":"a",')
    second = json.dumps('"title":"A"}]}')
    html = f"self.__next_f.push([1,{first}])" f"self.__next_f.push([1,{second}])"
    assert extract_events(html) == [{"slug": "a", "title": "A"}]


def test_extract_events_missing_returns_empty():
    assert extract_events("<html>no data here</html>") == []


if __name__ == "__main__":
    pytest.main([__file__])
