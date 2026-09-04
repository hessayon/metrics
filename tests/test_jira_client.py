import typing

import pytest

from teammetrics.config import ServiceConfig
from teammetrics.jira_client import JiraClient
from teammetrics.period import build_period


@typing.final
class FakeJira:
    def __init__(self) -> None:
        self.jql_calls: list[dict[str, typing.Any]] = []
        self.get_calls: list[tuple[str, dict[str, typing.Any]]] = []
        self.fail_agile = True

    def get_project(self, project: str) -> dict[str, str]:
        return {"key": project}

    def user_find_by_user_string(self, *, username: str, limit: int, start: int = 0) -> list[dict[str, str]]:
        del start, limit
        return [{"emailAddress": username.upper()}]

    def get_all_fields(self) -> list[dict[str, str]]:
        return [{"id": "customfield_42", "name": "Story Points"}]

    def jql(self, jql: str, *, fields: list[str], start: int, limit: int) -> dict[str, typing.Any]:
        self.jql_calls.append({"jql": jql, "fields": fields, "start": start, "limit": limit})
        return {
            "startAt": start,
            "total": 2,
            "issues": [{"key": f"CI-{start + 1}"}],
        }

    def resource_url(self, resource: str) -> str:
        return f"rest/api/2/{resource}"

    def get_agile_resource_url(self, resource: str, *, legacy_api: bool) -> str:
        return f"{'greenhopper' if legacy_api else 'agile'}/{resource}"

    def get_all_agile_boards(self, *, project_key: str, start: int, limit: int) -> dict[str, typing.Any]:
        del project_key, start, limit
        if self.fail_agile:
            raise RuntimeError("Agile API unavailable")
        return {"isLast": True, "values": [{"id": 1, "type": "scrum"}]}

    def get_all_sprints_from_board(self, board_id: int, *, start: int, limit: int) -> dict[str, typing.Any]:
        del board_id, start, limit
        return {"isLast": True, "values": [{"id": 10, "startDate": "2026-08-01T00:00:00+00:00"}]}

    def get(self, resource: str, *, params: dict[str, typing.Any]) -> dict[str, typing.Any]:
        self.get_calls.append((resource, params))
        if resource.startswith("agile/") and self.fail_agile:
            raise RuntimeError("Agile API unavailable")
        if resource.endswith("/changelog"):
            start = int(params["startAt"])
            return {"startAt": start, "total": 2, "values": [{"id": str(start + 1)}]}
        if resource.endswith("/board"):
            return {
                "isLast": True,
                "values": [
                    {"id": 1, "type": "scrum"},
                    {"id": 2, "type": "kanban"},
                    {"id": 3, "type": "scrum"},
                ],
            }
        return {"isLast": True, "values": [{"id": 10, "startDate": "2026-08-01T00:00:00+00:00"}]}


def make_client(fake_jira: FakeJira) -> JiraClient:
    config = ServiceConfig(url="https://jira.example", token="token", project="CI")
    return JiraClient(config, typing.cast("typing.Any", fake_jira))


def test_validates_project_employee_and_discovers_exact_story_points_field() -> None:
    client = make_client(FakeJira())

    assert client.project_exists()
    assert client.employee_exists("alice@example.com")
    assert client.discover_story_points_field() == "customfield_42"


def test_paginates_employee_search_until_exact_email_match() -> None:
    fake_jira = FakeJira()
    starts: list[int] = []

    def find_users(*, username: str, limit: int, start: int = 0) -> list[dict[str, str]]:
        starts.append(start)
        if start == 0:
            return [{"emailAddress": f"other-{index}@example.com"} for index in range(limit)]
        return [{"emailAddress": username.upper()}]

    fake_jira.user_find_by_user_string = find_users  # type: ignore[method-assign]

    assert make_client(fake_jira).employee_exists("alice@example.com")
    assert starts == [0, 50]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ([], "Jira field 'Story Points' not found"),
        (
            [{"id": "one", "name": "Story Points"}, {"id": "two", "name": "Story Points"}],
            "Multiple Jira fields named 'Story Points' found",
        ),
    ],
)
def test_rejects_missing_or_ambiguous_story_points_fields(
    fields: list[dict[str, str]], message: str
) -> None:
    fake_jira = FakeJira()
    fake_jira.get_all_fields = lambda: fields  # type: ignore[method-assign]

    with pytest.raises(ValueError, match=message):
        make_client(fake_jira).discover_story_points_field()


def test_paginates_widened_assignee_and_reporter_queries() -> None:
    fake_jira = FakeJira()
    client = make_client(fake_jira)
    period = build_period("2026-08-10", "2026-08-20")

    assigned = client.fetch_assigned_story_candidates("a@example.com", period, "customfield_42")
    created = client.fetch_created_story_candidates("a@example.com", period, "customfield_42")

    assert [issue["key"] for issue in assigned] == ["CI-1", "CI-2"]
    assert [issue["key"] for issue in created] == ["CI-1", "CI-2"]
    assert [call["start"] for call in fake_jira.jql_calls] == [0, 1, 0, 1]
    assert 'status CHANGED TO "Ready For IFT" AFTER "2026-08-08"' in fake_jira.jql_calls[0]["jql"]
    assert 'BEFORE "2026-08-23"' in fake_jira.jql_calls[0]["jql"]
    assert 'created < "2026-08-23"' in fake_jira.jql_calls[2]["jql"]
    assert "assignee" in fake_jira.jql_calls[0]["jql"]
    assert "reporter" in fake_jira.jql_calls[2]["jql"]


def test_fetches_complete_changelog_pages() -> None:
    fake_jira = FakeJira()

    histories = make_client(fake_jira).fetch_complete_changelog("CI-1")

    assert histories == [{"id": "1"}, {"id": "2"}]
    assert [params["startAt"] for resource, params in fake_jira.get_calls if resource.endswith("changelog")] == [0, 1]


def test_falls_back_to_greenhopper_filters_scrum_and_deduplicates_sprints() -> None:
    fake_jira = FakeJira()

    sprints = make_client(fake_jira).fetch_scrum_sprints()

    assert sprints is not None
    assert [sprint["id"] for sprint in sprints] == [10]
    assert any(resource == "greenhopper/board" for resource, _ in fake_jira.get_calls)
    assert not any(resource == "greenhopper/board/2/sprint" for resource, _ in fake_jira.get_calls)


def test_returns_none_when_both_agile_apis_fail() -> None:
    fake_jira = FakeJira()
    fake_jira.get = lambda resource, *, params: (  # type: ignore[method-assign]  # noqa: ARG005
        _ for _ in ()
    ).throw(RuntimeError(resource))

    assert make_client(fake_jira).fetch_scrum_sprints() is None
