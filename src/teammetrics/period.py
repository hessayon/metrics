import dataclasses
import datetime

INVALID_DATE_MESSAGE = "Invalid date format. Use YYYY-MM-DD."
REVERSED_PERIOD_MESSAGE = "--from must be on or before --to"


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Period:
    from_date: datetime.date
    to_date: datetime.date
    start: datetime.datetime
    end: datetime.datetime

    def contains(self, timestamp: datetime.datetime) -> bool:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("API timestamp must include a timezone")
        local_timestamp = timestamp.astimezone()
        return self.start <= local_timestamp < self.end

    def jira_candidate_dates(self) -> tuple[datetime.date, datetime.date]:
        padding = datetime.timedelta(days=2)
        return self.from_date - padding, self.to_date + datetime.timedelta(days=1) + padding


def build_period(from_value: str, to_value: str) -> Period:
    try:
        from_date = datetime.date.fromisoformat(from_value)
        to_date = datetime.date.fromisoformat(to_value)
    except ValueError as error:
        raise ValueError(INVALID_DATE_MESSAGE) from error
    if from_date.isoformat() != from_value or to_date.isoformat() != to_value:
        raise ValueError(INVALID_DATE_MESSAGE)
    if from_date > to_date:
        raise ValueError(REVERSED_PERIOD_MESSAGE)

    start = datetime.datetime.combine(from_date, datetime.time.min).astimezone()
    end = datetime.datetime.combine(to_date + datetime.timedelta(days=1), datetime.time.min).astimezone()
    return Period(from_date=from_date, to_date=to_date, start=start, end=end)


def parse_api_timestamp(timestamp_value: str) -> datetime.datetime:
    parsed_timestamp = datetime.datetime.fromisoformat(timestamp_value)
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise ValueError("API timestamp must include a timezone")
    return parsed_timestamp.astimezone()
