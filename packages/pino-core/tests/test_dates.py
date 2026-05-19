from pino_core.dates import parse_source_date_range, parse_source_datetime, utc_iso


def test_parse_source_datetime_assumes_vilnius_timezone() -> None:
    value = parse_source_datetime("2026-07-18 15:00:00")

    assert value is not None
    assert utc_iso(value) == "2026-07-18T12:00:00+00:00"


def test_parse_source_date_range_expands_date_only_end() -> None:
    start, end = parse_source_date_range("2026-03-27 - 2026-06-21")

    assert start is not None
    assert end is not None
    assert utc_iso(start) == "2026-03-26T22:00:00+00:00"
    assert utc_iso(end) == "2026-06-21T20:59:59.999999+00:00"
