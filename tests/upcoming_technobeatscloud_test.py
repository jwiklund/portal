import pytest

from born_portal.upcoming.sources.technobeatscloud import (
    build_url,
    parse_events,
)


def _row(**overrides):
    row = {
        "id": "1",
        "slug": "dimension-pre-party-slakthuset-2026-11-13",
        "name": "DIMENSION - PRE PARTY - FREE ENTRY UNTIL 23:00",
        "start_date": "2026-11-13",
        "start_time": "22:00",
        "computed_venue_name": "Slakthuset",
        "venue_name_override": None,
        "min_price": 100,
        "min_currency": "SEK",
        "location_label": "Estocolmo, Stockholm, SE",
        "city_name": "Estocolmo",
    }
    row.update(overrides)
    return row


def _payload(*rows):
    return {"markers": [], "events": list(rows), "totalMatching": len(rows)}


def test_parse_full_event():
    events = parse_events(_payload(_row()), "2026-11-13", "2026-11-15")

    assert len(events) == 1
    event = events[0]
    assert (
        event.url == "https://technobeatscloud.com/en/events/event/"
        "dimension-pre-party-slakthuset-2026-11-13"
    )
    assert event.name == "DIMENSION - PRE PARTY - FREE ENTRY UNTIL 23:00"
    assert event.description == ""
    assert event.location == "Slakthuset"
    assert event.price == "100 SEK"
    assert event.date == "2026-11-13 22:00"
    assert event.ticket is True


def test_parse_price_whole_float_trims_decimal():
    events = parse_events(_payload(_row(min_price=100.0)), "2026-11-13", "2026-11-13")
    assert events[0].price == "100 SEK"


def test_parse_price_float_keeps_decimals():
    events = parse_events(_payload(_row(min_price=120.5)), "2026-11-13", "2026-11-13")
    assert events[0].price == "120.5 SEK"


def test_parse_missing_price_is_none_and_not_ticketed():
    events = parse_events(
        _payload(_row(min_price=None, min_currency=None)),
        "2026-11-13",
        "2026-11-13",
    )
    assert events[0].price is None
    assert events[0].ticket is False


def test_parse_zero_price_not_ticketed():
    events = parse_events(_payload(_row(min_price=0)), "2026-11-13", "2026-11-13")
    assert events[0].price == "0 SEK"
    assert events[0].ticket is False


def test_parse_venue_override_takes_precedence():
    events = parse_events(
        _payload(_row(venue_name_override="Secret Location")),
        "2026-11-13",
        "2026-11-13",
    )
    assert events[0].location == "Secret Location"


def test_parse_location_falls_back_to_label():
    events = parse_events(
        _payload(_row(computed_venue_name=None, venue_name_override=None)),
        "2026-11-13",
        "2026-11-13",
    )
    assert events[0].location == "Estocolmo, Stockholm, SE"


def test_parse_location_none_when_all_empty():
    events = parse_events(
        _payload(
            _row(
                venue_name_override=None,
                computed_venue_name="",
                location_label=None,
            )
        ),
        "2026-11-13",
        "2026-11-13",
    )
    assert events[0].location is None


def test_parse_date_without_time():
    events = parse_events(_payload(_row(start_time=None)), "2026-11-13", "2026-11-13")
    assert events[0].date == "2026-11-13"


def test_parse_filters_out_of_range():
    payload = _payload(
        _row(slug="in", start_date="2026-11-13"),
        _row(slug="before", start_date="2026-11-12"),
        _row(slug="after", start_date="2026-11-16"),
    )
    events = parse_events(payload, "2026-11-13", "2026-11-15")
    assert [event.url.rsplit("/", 1)[-1] for event in events] == ["in"]


def test_parse_skips_entries_without_slug_or_date():
    payload = _payload(_row(slug=None), _row(start_date=None), _row(slug="ok"))
    events = parse_events(payload, "2026-11-13", "2026-11-13")
    assert [event.url.rsplit("/", 1)[-1] for event in events] == ["ok"]


def test_parse_empty_payload():
    assert parse_events({}, "2026-11-13", "2026-11-13") == []


def test_build_url_contains_range_and_bbox():
    url = build_url("2026-11-13", "2026-11-15")
    assert url.startswith(
        "https://technobeatscloud.com/api/agenda/map-events?locale=en"
    )
    assert "from=2026-11-13" in url
    assert "to=2026-11-15" in url
    assert "bbox=17.6087%2C59.0994%2C18.5214%2C59.5658" in url
    assert "tz=Europe%2FStockholm" in url


if __name__ == "__main__":
    pytest.main([__file__])
