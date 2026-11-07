import pytest

from born_portal.upcoming.sources.raveoclock import parse_ical

# Hand-written sample: includes a folded (continuation) line, an escaped comma
# in LOCATION, an HTML DESCRIPTION with a literal ``\n`` and entities, and an
# event whose local start date falls outside the requested range.
ICS = r"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART:20261106T220000Z
DTEND:20261107T040000Z
UID:inrange@google.com
SUMMARY:Test Party\, Part One — a very long title that gets fol
 ded here
DESCRIPTION:<p>Hello &amp; welcome</p>\n<p>Second line</p>
LOCATION:Under Bron\, Hammarby slussväg 2\, Stockholm
END:VEVENT
BEGIN:VEVENT
DTSTART:20261031T210000Z
DTEND:20261101T030000Z
UID:outofrange@google.com
SUMMARY:Old Party
DESCRIPTION:<p>Nope</p>
LOCATION:Somewhere
END:VEVENT
END:VCALENDAR
"""


def test_parse_ical_filters_and_maps():
    events = parse_ical(ICS, "2026-11-06", "2026-11-08")

    assert len(events) == 1
    event = events[0]
    assert event.url == "https://raveoclock.se/#inrange@google.com"
    assert event.name == (
        "Test Party, Part One — a very long title that gets folded here"
    )
    assert event.description == "Hello & welcome Second line"
    assert event.location == "Under Bron, Hammarby slussväg 2, Stockholm"
    assert event.price is None
    assert event.ticket is False
    # 22:00 UTC -> 23:00 CET; 04:00 UTC -> 05:00 CET (11 Nov is CET, UTC+1).
    assert event.date == "2026-11-06 23:00 - 2026-11-07 05:00"


def test_parse_ical_excludes_out_of_range():
    events = parse_ical(ICS, "2026-10-30", "2026-11-01")

    assert [e.url for e in events] == ["https://raveoclock.se/#outofrange@google.com"]


def test_parse_ical_handles_date_only_event():
    ics = r"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261107
DTEND;VALUE=DATE:20261108
UID:allday@google.com
SUMMARY:All Day Party
END:VEVENT
END:VCALENDAR
"""

    events = parse_ical(ics, "2026-11-07", "2026-11-07")

    assert len(events) == 1
    assert events[0].date == "2026-11-07 - 2026-11-08"


def test_parse_ical_prefers_ticket_link_from_description():
    ics = r"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20261107T220000Z
UID:withlink@google.com
SUMMARY:Linked Party
DESCRIPTION:<p>Tickets: <a href="https://billetto.se/e/123">buy</a></p>
LOCATION:Under Bron
END:VEVENT
END:VCALENDAR
"""

    events = parse_ical(ics, "2026-11-07", "2026-11-08")

    assert len(events) == 1
    assert events[0].url == "https://billetto.se/e/123"


def test_parse_ical_skips_social_links_for_fallback():
    ics = r"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20261107T220000Z
UID:social@google.com
SUMMARY:Social Party
DESCRIPTION:Follow us https://www.instagram.com/club/ and https://t.me/club
LOCATION:Under Bron
END:VEVENT
END:VCALENDAR
"""

    events = parse_ical(ics, "2026-11-07", "2026-11-08")

    assert len(events) == 1
    assert events[0].url == "https://raveoclock.se/#social@google.com"


if __name__ == "__main__":
    pytest.main([__file__])
