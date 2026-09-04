import datetime
import typing

from teammetrics.jira_metrics import build_jira_metrics
from teammetrics.period import Period, build_period


def timestamp(period: Period, days: int) -> str:
    return (period.start + datetime.timedelta(days=days)).isoformat()


def history(period: Period, days: int, field: str, from_value: str | None, to_value: str) -> dict[str, typing.Any]:
    return {
        "created": timestamp(period, days),
        "items": [{"field": field, "from": from_value, "to": to_value, "toString": to_value}],
    }


def story(
    key: str,
    points: int | None,
    created: str,
    histories: list[dict[str, typing.Any]],
) -> dict[str, typing.Any]:
    return {
        "key": key,
        "fields": {"created": created, "customfield_42": points},
        "changelog": {"histories": histories},
    }


def sprint(sprint_id: int, period: Period, start_days: int, end_days: int) -> dict[str, typing.Any]:
    return {
        "id": sprint_id,
        "startDate": timestamp(period, start_days),
        "endDate": timestamp(period, end_days),
    }


def test_calculates_jira_metrics_from_actual_transitions_and_complete_links() -> None:
    period = build_period("2026-08-01", "2026-08-31")
    first = story(
        "CI-1",
        5,
        timestamp(period, 0),
        [
            history(period, -10, "Sprint", None, "1"),
            history(period, 1, "status", None, "work started"),
            history(period, 4, "Sprint", "1", "2"),
            history(period, 9, "status", None, "Ready For IFT"),
            history(period, 11, "status", None, "Ready For IFT"),
        ],
    )
    second = story(
        "CI-2",
        3,
        timestamp(period, 31),
        [
            history(period, -10, "Sprint", None, "2"),
            history(period, 6, "status", None, "in progress"),
            history(period, 8, "status", None, "Ready For IFT"),
        ],
    )
    not_delivered = story(
        "CI-3",
        13,
        timestamp(period, 30),
        [history(period, 3, "status", None, "Done")],
    )
    sprints = [sprint(1, period, -8, 4), sprint(2, period, 4, 19), sprint(3, period, 19, 35)]

    report = build_jira_metrics(
        [first, second, not_delivered],
        [first, second, not_delivered],
        sprints,
        period,
        "customfield_42",
        "https://jira.example/",
    )

    assert report["metrics"] == {
        "total_story_points": 8,
        "stories_delivered": 2,
        "stories_created": 2,
        "stories_carried_over": 1,
        "carry_over_percentage": 50.0,
        "average_cycle_time_days": 5.0,
        "average_sp_per_sprint": 2.7,
    }
    assert report["links"]["delivered_stories"] == [
        {"key": "CI-1", "url": "https://jira.example/browse/CI-1", "points": 5},
        {"key": "CI-2", "url": "https://jira.example/browse/CI-2", "points": 3},
    ]
    assert [link["key"] for link in report["links"]["created_stories"]] == ["CI-1", "CI-3"]


def test_unset_points_missing_pairs_and_unavailable_agile_have_defined_defaults() -> None:
    period = build_period("2026-08-01", "2026-08-31")
    delivered = story(
        "CI-1",
        None,
        timestamp(period, 0),
        [history(period, 2, "status", None, "Ready For IFT")],
    )

    report = build_jira_metrics(
        [delivered],
        [],
        None,
        period,
        "customfield_42",
        "https://jira.example",
    )

    assert report["metrics"] == {
        "total_story_points": 0,
        "stories_delivered": 1,
        "stories_created": 0,
        "stories_carried_over": 0,
        "carry_over_percentage": 0.0,
        "average_cycle_time_days": None,
        "average_sp_per_sprint": None,
    }


def test_ambiguous_active_sprint_is_unknown() -> None:
    period = build_period("2026-08-01", "2026-08-31")
    delivered = story(
        "CI-1",
        5,
        timestamp(period, 0),
        [
            history(period, -1, "Sprint", None, "1,2"),
            history(period, 1, "status", None, "work started"),
            history(period, 2, "status", None, "Ready For IFT"),
        ],
    )
    sprints = [sprint(1, period, 0, 10), sprint(2, period, 0, 10)]

    report = build_jira_metrics(
        [delivered],
        [],
        sprints,
        period,
        "customfield_42",
        "https://jira.example",
    )

    assert report["metrics"]["stories_carried_over"] == 0
    assert report["metrics"]["average_sp_per_sprint"] == 0.0
