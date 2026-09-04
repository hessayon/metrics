import datetime

import pytest

from teammetrics.period import build_period, parse_api_timestamp


def test_builds_inclusive_local_date_period_as_half_open_interval() -> None:
    period = build_period("2026-08-01", "2026-08-31")

    assert period.from_date == datetime.date(2026, 8, 1)
    assert period.to_date == datetime.date(2026, 8, 31)
    assert period.start.hour == 0
    assert period.end.date() == datetime.date(2026, 9, 1)
    assert period.end.hour == 0
    assert period.start.tzinfo is not None
    assert period.end.tzinfo is not None


def test_checks_timestamp_after_converting_to_local_timezone() -> None:
    period = build_period("2026-08-01", "2026-08-01")
    boundary_in_utc = period.end.astimezone(datetime.UTC)

    assert period.contains(period.start.astimezone(datetime.UTC))
    assert not period.contains(boundary_in_utc)


def test_widens_jira_candidate_dates_by_two_days_at_each_edge() -> None:
    period = build_period("2026-08-10", "2026-08-20")

    assert period.jira_candidate_dates() == (datetime.date(2026, 8, 8), datetime.date(2026, 8, 23))


def test_parses_api_timestamp_in_local_timezone() -> None:
    parsed_timestamp = parse_api_timestamp("2026-08-01T00:30:00+03:00")

    assert parsed_timestamp.tzinfo is not None
    expected_timestamp = datetime.datetime(
        2026,
        8,
        1,
        0,
        30,
        tzinfo=datetime.timezone(datetime.timedelta(hours=3)),
    )
    assert parsed_timestamp == expected_timestamp


def test_rejects_timezone_free_api_timestamp() -> None:
    with pytest.raises(ValueError, match="must include a timezone"):
        parse_api_timestamp("2026-08-01T00:30:00")
