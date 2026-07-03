import locale
import re
from datetime import date, datetime

locale.setlocale(locale.LC_TIME, "sv_SE.UTF-8")  # Set Swedish locale for date parsing

_formats = [
    ("%d %b %Y %H:%M", "datetime"),  # Swedish date with time (e.g. "23 maj 2026 18:00")
    (
        "%d %B %Y %H:%M",
        "datetime",
    ),  # Swedish date with time (e.g. "23 maj 2026 18:00") - full month name
    ("%d %b %Y", "date"),  # Swedish date only (e.g. "23 maj 2026")
    ("%d %B %Y", "date"),  # Swedish date only (e.g. "23 maj 2026") - full month name
    (
        "%b %d, %Y, %H:%M",
        "en-datetime",
    ),  # English date with time (e.g. "May 23, 2026, 18:00")
    (
        "%B %d, %Y, %H:%M",
        "en-datetime",
    ),  # English date with time (e.g. "May 23, 2026, 18:00") - full month name
    ("%b %d, %Y", "en-date"),  # English date only (e.g. "May 23, 2026")
    (
        "%B %d, %Y",
        "en-date",
    ),  # English date only (e.g. "May 23, 2026") - full month name
    ("%Y-%m-%d %H:%M", "datetime"),  # ISO date with time (e.g. "2026-05-23 18:00")
    ("%Y-%m-%dT%H:%M", "datetime"),  # ISO date with time (e.g. "2026-05-23T18:00")
    (
        "%Y-%m-%dT%H:%MZ",
        "datetime",
    ),  # ISO date with time and Zulu timezone (e.g. "2026-05-23T18:00Z")
    (
        "%Y-%m-%dT%H:%M:%SZ",
        "datetime",
    ),  # ISO timestamp with Z (e.g. "2026-05-23T01:02:03Z")
    (
        "%Y-%m-%dT%H:%M:%S%z",
        "datetime-tz",
    ),  # ISO timestamp with offset (e.g. "2026-05-23T01:02:03+02:00")
    ("%Y-%m-%dT%H:%M:%S", "datetime"),  # ISO timestamp (e.g. "2026-05-23T01:02:03")
    (
        "%Y-%m-%d %H:%M:%S",
        "datetime",
    ),  # ISO date with time (e.g. "2026-05-23 01:02:03")
    ("%Y-%m-%d", "date"),  # ISO date only (e.g. "2026-05-23")
    ("%H:%M", "time"),  # Time only (e.g. "18:00")
]

_ENGLISH_TO_SWEDISH_MONTHS = {
    # Full names
    "january": "januari",
    "february": "februari",
    "march": "mars",
    "april": "april",
    "may": "maj",
    "june": "juni",
    "july": "juli",
    "august": "augusti",
    "september": "september",
    "october": "oktober",
    "november": "november",
    "december": "december",
    # Abbreviated
    "jan": "jan",
    "feb": "feb",
    "mar": "mar",
    "apr": "apr",
    "jun": "jun",
    "jul": "jul",
    "aug": "aug",
    "sep": "sep",
    "oct": "okt",
    "nov": "nov",
    "dec": "dec",
}


def _english_to_swedish_date(date_str: str) -> str:
    def replace_month(match):
        word = match.group(0)
        return _ENGLISH_TO_SWEDISH_MONTHS.get(word.lower(), word)

    return re.sub(r"[A-Za-z]+", replace_month, date_str)


def _parse_date(date_str: str) -> str | None:
    """Try to parse a date string, return ISO format or None.

    Tries Swedish locale (e.g. '23 maj 2026') first, then ISO format.
    """
    if not date_str:
        return None
    date_str = date_str.strip()

    for format, format_type in _formats:
        try:
            if format_type.startswith("en-"):
                dt = datetime.strptime(_english_to_swedish_date(date_str), format)
            elif format_type == "datetime-tz":
                # Normalize timezone offset: "+02:00" -> "+0200"
                dt = datetime.strptime(
                    re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", date_str), format
                )
            else:
                dt = datetime.strptime(date_str, format)
        except ValueError:
            continue
        if dt:
            if "datetime" in format_type:
                return dt.strftime("%Y-%m-%d %H:%M")
            elif "date" in format_type:
                return dt.strftime("%Y-%m-%d")
            else:
                return dt.strftime("%H:%M")

    return None


def _format_date_range(
    start_date: str,
    start_time: str,
    end_date: str,
    end_time: str,
) -> str:
    """Format a date range, omitting redundant date parts if possible."""
    if not start_time:
        return f"{start_date} - {end_date}" if end_date else start_date

    if not end_time:
        return f"{start_date} {start_time}"

    if start_date == end_date or not end_date:
        return f"{start_date} {start_time} - {end_time}"

    return f"{start_date} {start_time} - {end_date} {end_time}"


def parse_date_range(date_str: str) -> str:
    """Parse a date string that may contain time ranges or full date ranges.

    Supports formats:
    - "2026-05-23 18:00-21:00" (ISO date + time range)
    - "2026-05-23 18:00" (ISO date + time)
    - "23 maj 2026 18:00-21:00" (Swedish date + time range)
    - "23 maj 2026 18:00" (Swedish date + time)
    - "23 maj 2026 18:00 - 24 maj 2026 21:00" (full Swedish date range)
    - "2026-05-23 18:00 - 2026-05-24 21:00" (full ISO date range)
    - "2026-05-23" (just a date)
    - "2026-05-23T01:02:03Z" (full ISO timestamp)

    Returns a formatted date range string.
    """
    if not date_str:
        return date_str

    date_str = date_str.replace("–", "-")
    dash_indexes = [m.start() for m in re.finditer(r"-", date_str)]

    for dash_index in dash_indexes:
        first = _parse_date(date_str[:dash_index])
        second = _parse_date(date_str[dash_index + 1 :])

        if not first or not second:
            continue

        if " " in first:
            first_date, first_time = first.split(" ", 1)
        elif len(first) == 5:
            first_date, first_time = None, first
        else:
            first_date, first_time = first, None
        if " " in second:
            second_date, second_time = second.split(" ", 1)
        elif len(second) == 5:
            second_date, second_time = None, second
        else:
            second_date, second_time = second, None

        return _format_date_range(first_date, first_time, second_date, second_time)

    date = _parse_date(date_str)
    if date:
        return date

    return date_str
