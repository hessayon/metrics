import datetime
import re
import statistics
import typing

from teammetrics.period import Period, parse_api_timestamp

WORK_STARTED_STATUSES = frozenset({"work started", "in progress"})
SPRINT_ID_PATTERN = re.compile(r"(?:^|,)\s*(\d+)\s*(?=,|$)")
LEGACY_SPRINT_ID_PATTERN = re.compile(r"\bid=(\d+)\b")
MINIMUM_CYCLE_COUNT = 2


def build_jira_metrics(  # noqa: PLR0913, PLR0917
    assigned_stories: list[dict[str, typing.Any]],
    created_candidates: list[dict[str, typing.Any]],
    sprints: list[dict[str, typing.Any]] | None,
    period: Period,
    story_points_field: str,
    jira_url: str,
) -> dict[str, typing.Any]:
    delivered = _build_delivered_stories(assigned_stories, period, story_points_field)
    created = [story for story in created_candidates if _created_in_period(story, period)]
    known_sprints = _parse_sprints(sprints or []) if sprints is not None else {}
    period_sprints = {
        sprint_id: boundaries
        for sprint_id, boundaries in known_sprints.items()
        if boundaries[0] < period.end and boundaries[1] > period.start
    }
    cycle_days = [
        (story["delivery"] - story["work_start"]).total_seconds() / 86400
        for story in delivered
        if story["work_start"] is not None
    ]

    carried_over = 0
    sprint_points = dict.fromkeys(period_sprints, 0.0)
    if sprints is not None:
        for story in delivered:
            delivery_sprint = _resolve_sprint_at(story["issue"], story["delivery"], known_sprints)
            if delivery_sprint in sprint_points:
                sprint_points[delivery_sprint] += story["points"]
            if story["work_start"] is None:
                continue
            start_sprint = _resolve_sprint_at(story["issue"], story["work_start"], known_sprints)
            carried_over += int(
                start_sprint is not None and delivery_sprint is not None and start_sprint != delivery_sprint
            )

    delivered_count = len(delivered)
    return {
        "metrics": {
            "total_story_points": _clean_number(sum(story["points"] for story in delivered)),
            "stories_delivered": delivered_count,
            "stories_created": len(created),
            "stories_carried_over": carried_over,
            "carry_over_percentage": round(carried_over / delivered_count * 100, 1) if delivered_count else 0.0,
            "average_cycle_time_days": (
                round(statistics.fmean(cycle_days), 1) if len(cycle_days) >= MINIMUM_CYCLE_COUNT else None
            ),
            "average_sp_per_sprint": round(statistics.fmean(sprint_points.values()), 1) if sprint_points else None,
        },
        "links": {
            "delivered_stories": [_story_link(story["issue"], story["points"], jira_url) for story in delivered],
            "created_stories": [
                _story_link(story, _story_points(story, story_points_field), jira_url) for story in created
            ],
        },
    }


def _build_delivered_stories(
    issues: list[dict[str, typing.Any]], period: Period, story_points_field: str
) -> list[dict[str, typing.Any]]:
    delivered: list[dict[str, typing.Any]] = []
    for issue in issues:
        status_events = _status_events(issue)
        delivery = next(
            (
                timestamp
                for timestamp, status in status_events
                if status == "ready for ift" and period.contains(timestamp)
            ),
            None,
        )
        if delivery is None:
            continue
        work_start = next(
            (
                timestamp
                for timestamp, status in reversed(status_events)
                if timestamp < delivery and status in WORK_STARTED_STATUSES
            ),
            None,
        )
        delivered.append({
            "issue": issue,
            "delivery": delivery,
            "work_start": work_start,
            "points": _story_points(issue, story_points_field),
        })
    return delivered


def _status_events(issue: dict[str, typing.Any]) -> list[tuple[datetime.datetime, str]]:
    events: list[tuple[datetime.datetime, str]] = []
    for history in _histories(issue):
        timestamp = _history_timestamp(history)
        if timestamp is None:
            continue
        for item in history.get("items", []):
            if str(item.get("field", "")).casefold() == "status":
                events.append((timestamp, str(item.get("toString", "")).strip().casefold()))  # noqa: PERF401
    return sorted(events)


def _resolve_sprint_at(
    issue: dict[str, typing.Any],
    event_time: datetime.datetime,
    sprints: dict[int, tuple[datetime.datetime, datetime.datetime]],
) -> int | None:
    changes: list[tuple[datetime.datetime, set[int], set[int]]] = []
    for history in _histories(issue):
        timestamp = _history_timestamp(history)
        if timestamp is None:
            continue
        for item in history.get("items", []):
            if str(item.get("field", "")).casefold() == "sprint":
                changes.append(  # noqa: PERF401
                    (timestamp, _sprint_ids(item.get("from")), _sprint_ids(item.get("to")))
                )
    changes.sort(key=lambda change: change[0])
    membership = changes[0][1].copy() if changes else set()
    for timestamp, _, changed_membership in changes:
        if timestamp > event_time:
            break
        membership = changed_membership.copy()
    matches = [
        sprint_id
        for sprint_id in membership
        if sprint_id in sprints and sprints[sprint_id][0] <= event_time < sprints[sprint_id][1]
    ]
    return matches[0] if len(matches) == 1 else None


def _parse_sprints(
    raw_sprints: list[dict[str, typing.Any]],
) -> dict[int, tuple[datetime.datetime, datetime.datetime]]:
    parsed: dict[int, tuple[datetime.datetime, datetime.datetime]] = {}
    for sprint in raw_sprints:
        try:
            sprint_id = int(sprint["id"])
            sprint_start = parse_api_timestamp(str(sprint["startDate"]))
            sprint_end = parse_api_timestamp(str(sprint["endDate"]))
        except (KeyError, TypeError, ValueError):
            continue
        parsed.setdefault(sprint_id, (sprint_start, sprint_end))
    return parsed


def _histories(issue: dict[str, typing.Any]) -> list[dict[str, typing.Any]]:
    changelog = issue.get("changelog", {})
    histories = changelog.get("histories", []) if isinstance(changelog, dict) else changelog
    return histories if isinstance(histories, list) else []


def _history_timestamp(history: dict[str, typing.Any]) -> datetime.datetime | None:
    try:
        return parse_api_timestamp(str(history["created"]))
    except (KeyError, ValueError):
        return None


def _sprint_ids(value: object) -> set[int]:
    if isinstance(value, list):
        return {int(sprint_id) for sprint_id in value if str(sprint_id).isdigit()}
    if value is None:
        return set()
    text_value = str(value).strip().strip("[]")
    matches = LEGACY_SPRINT_ID_PATTERN.findall(text_value) or SPRINT_ID_PATTERN.findall(text_value)
    return {int(match) for match in matches}


def _created_in_period(issue: dict[str, typing.Any], period: Period) -> bool:
    try:
        return period.contains(parse_api_timestamp(str(issue["fields"]["created"])))
    except (KeyError, TypeError, ValueError):
        return False


def _story_points(issue: dict[str, typing.Any], story_points_field: str) -> float:
    value = issue.get("fields", {}).get(story_points_field)
    return float(value) if isinstance(value, int | float) else 0.0


def _story_link(issue: dict[str, typing.Any], points: float, jira_url: str) -> dict[str, typing.Any]:
    issue_key = str(issue["key"])
    return {"key": issue_key, "url": f"{jira_url.rstrip('/')}/browse/{issue_key}", "points": _clean_number(points)}


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value
