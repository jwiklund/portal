import pytest

from born_portal.utils.date_range import parse_date_range


def test_empty_string():
    result = parse_date_range("")
    assert result == ""


def test_none_string():
    result = parse_date_range(None)
    assert result == None


def test_invalid_string():
    result = parse_date_range("garbage input here")
    assert result == "garbage input here"


def test_iso_date_only():
    result = parse_date_range("2026-05-23")
    assert result == "2026-05-23"


def test_iso_date_with_time():
    result = parse_date_range("2026-05-23 18:00")
    assert result == "2026-05-23 18:00"


def test_iso_date_with_time_range():
    result = parse_date_range("2026-05-23 18:00-21:00")
    assert result == "2026-05-23 18:00 - 21:00"


def test_iso_full_date_range_same_day():
    result = parse_date_range("2026-05-23 18:00 - 2026-05-23 21:00")
    assert result == "2026-05-23 18:00 - 21:00"


def test_iso_full_date_range():
    result = parse_date_range("2026-05-23 18:00 - 2026-05-24 21:00")
    assert result == "2026-05-23 18:00 - 2026-05-24 21:00"


def test_swedish_date_with_time():
    result = parse_date_range("23 maj 2026 18:00")
    assert result == "2026-05-23 18:00"


def test_swedish_date_with_time_range():
    result = parse_date_range("23 maj 2026 18:00-21:00")
    assert result == "2026-05-23 18:00 - 21:00"


def test_swedish_full_date_range():
    result = parse_date_range("23 maj 2026 18:00 - 24 maj 2026 21:00")
    assert result == "2026-05-23 18:00 - 2026-05-24 21:00"


def test_swedish_full_date_range_same_day():
    result = parse_date_range("23 maj 2026 18:00 - 23 maj 2026 21:00")
    assert result == "2026-05-23 18:00 - 21:00"


def test_swedish_single_digit_day():
    result = parse_date_range("3 juni 2025 09:00-12:00")
    assert result == "2025-06-03 09:00 - 12:00"


def test_swedish_date_only():
    result = parse_date_range("23 maj 2026")
    assert result == "2026-05-23"


def test_swedish_full_date_range_reverse_order():
    """Test that the full date range regex handles month names correctly."""
    result = parse_date_range("1 januari 2026 10:00 - 2 januari 2026 18:00")
    assert result == "2026-01-01 10:00 - 2026-01-02 18:00"


def test_various_swedish_months():
    """Test Swedish month names: januari, februari, mars, april, maj, juni,
    juli, augusti, september, oktober, november, december."""
    test_data = [
        ("1 januari 2026 10:00", "2026-01-01 10:00"),
        ("14 februari 2026 14:00", "2026-02-14 14:00"),
        ("5 mars 2026 09:00", "2026-03-05 09:00"),
        ("20 april 2026 18:00", "2026-04-20 18:00"),
        ("15 maj 2026 12:00", "2026-05-15 12:00"),
        ("30 juni 2026", "2026-06-30"),
        ("12 juli 2026 20:00", "2026-07-12 20:00"),
        ("25 augusti 2026 16:00", "2026-08-25 16:00"),
        ("10 september 2026 11:00", "2026-09-10 11:00"),
        ("31 oktober 2026 22:00", "2026-10-31 22:00"),
        ("7 november 2026 15:00", "2026-11-07 15:00"),
        ("24 december 2026 17:00", "2026-12-24 17:00"),
        ("May 30, 2026, 21:00-03:00", "2026-05-30 21:00 - 03:00"),
    ]
    for date_input, expected_date in test_data:
        result = parse_date_range(date_input)
        assert result == expected_date, f"Failed for {date_input}: got {result}"


if __name__ == "__main__":
    pytest.main([__file__])
