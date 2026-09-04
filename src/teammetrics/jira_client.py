import collections.abc
import typing

import requests
from atlassian import Jira

from teammetrics.config import ServiceConfig
from teammetrics.period import Period

PAGE_SIZE = 50


@typing.final
class JiraClient:
    def __init__(self, config: ServiceConfig, jira: Jira | None = None) -> None:
        self.config = config
        self.jira = jira or Jira(url=config.url, token=config.token)

    def project_exists(self) -> bool:
        try:
            return bool(self.jira.get_project(self.config.project))
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == requests.codes.not_found:
                return False
            raise

    def employee_exists(self, email: str) -> bool:
        start = 0
        while True:
            if start:
                response = self.jira.user_find_by_user_string(username=email, start=start, limit=PAGE_SIZE)
            else:
                response = self.jira.user_find_by_user_string(username=email, limit=PAGE_SIZE)
            users = response.get("users", []) if isinstance(response, dict) else response
            if not isinstance(users, list):
                return False
            if any(
                isinstance(user, dict) and str(user.get("emailAddress", "")).casefold() == email.casefold()
                for user in users
            ):
                return True
            if len(users) < PAGE_SIZE:
                return False
            start += len(users)

    def discover_story_points_field(self) -> str:
        response = self.jira.get_all_fields() or []
        fields = response.get("values", []) if isinstance(response, dict) else response
        matches = [field["id"] for field in fields if field.get("name") == "Story Points"]
        if not matches:
            raise ValueError("Jira field 'Story Points' not found")
        if len(matches) > 1:
            raise ValueError("Multiple Jira fields named 'Story Points' found")
        return str(matches[0])

    def fetch_assigned_story_candidates(
        self, email: str, period: Period, story_points_field: str
    ) -> list[dict[str, typing.Any]]:
        candidate_from, candidate_to = period.jira_candidate_dates()
        jql = (
            f'project = "{_escape_jql(self.config.project)}" AND issuetype = Story '
            f'AND assignee = "{_escape_jql(email)}" '
            f'AND status CHANGED TO "Ready For IFT" AFTER "{candidate_from.isoformat()}" '
            f'BEFORE "{candidate_to.isoformat()}"'
        )
        return self._fetch_issues(jql, ["created", "status", story_points_field])

    def fetch_created_story_candidates(
        self, email: str, period: Period, story_points_field: str
    ) -> list[dict[str, typing.Any]]:
        candidate_from, candidate_to = period.jira_candidate_dates()
        jql = (
            f'project = "{_escape_jql(self.config.project)}" AND issuetype = Story '
            f'AND reporter = "{_escape_jql(email)}" '
            f'AND created >= "{candidate_from.isoformat()}" AND created < "{candidate_to.isoformat()}"'
        )
        return self._fetch_issues(jql, ["created", story_points_field])

    def fetch_complete_changelog(self, issue_key: str) -> list[dict[str, typing.Any]]:
        resource = self.jira.resource_url(f"issue/{issue_key}/changelog")
        return self._fetch_pages(
            lambda start: self.jira.get(resource, params={"startAt": start, "maxResults": PAGE_SIZE}),
            "values",
        )

    def attach_complete_changelogs(self, issues: list[dict[str, typing.Any]]) -> list[dict[str, typing.Any]]:
        for issue in issues:
            issue["changelog"] = {"histories": self.fetch_complete_changelog(str(issue["key"]))}
        return issues

    def fetch_scrum_sprints(self) -> list[dict[str, typing.Any]] | None:
        try:
            return self._fetch_scrum_sprints(legacy_api=False)
        except Exception:  # noqa: BLE001 - optional remote capability; retry through the documented DC fallback
            try:
                return self._fetch_scrum_sprints(legacy_api=True)
            except Exception:  # noqa: BLE001 - absence of both optional Agile endpoints is a valid result
                return None

    def _fetch_issues(self, jql: str, fields: list[str]) -> list[dict[str, typing.Any]]:
        return self._fetch_pages(
            lambda start: self.jira.jql(jql, fields=fields, start=start, limit=PAGE_SIZE),
            "issues",
        )

    def _fetch_scrum_sprints(self, *, legacy_api: bool) -> list[dict[str, typing.Any]]:
        if legacy_api:
            boards = self._fetch_agile_pages(
                "board",
                legacy_api=True,
                values_keys=("values", "views"),
                params={"projectKeyOrId": self.config.project},
            )
        else:
            boards = self._fetch_pages(
                lambda start: self.jira.get_all_agile_boards(
                    project_key=self.config.project, start=start, limit=PAGE_SIZE
                ),
                "values",
            )
        sprints_by_id: dict[int, dict[str, typing.Any]] = {}
        for board in boards:
            if str(board.get("type", "")).casefold() != "scrum":
                continue
            if legacy_api:
                board_sprints = self._fetch_agile_pages(
                    f"board/{board['id']}/sprint", legacy_api=True, values_keys=("values", "sprints")
                )
            else:
                board_sprints = self._fetch_pages(
                    lambda start, board_id=board["id"]: self.jira.get_all_sprints_from_board(
                        board_id, start=start, limit=PAGE_SIZE
                    ),
                    "values",
                )
            for sprint in board_sprints:
                try:
                    sprint_id = int(sprint["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                sprints_by_id.setdefault(sprint_id, sprint)
        return list(sprints_by_id.values())

    def _fetch_agile_pages(
        self,
        resource: str,
        *,
        legacy_api: bool,
        values_keys: tuple[str, ...] = ("values",),
        params: dict[str, typing.Any] | None = None,
    ) -> list[dict[str, typing.Any]]:
        resource_url = self.jira.get_agile_resource_url(resource, legacy_api=legacy_api)

        def fetch_page(start: int) -> object:
            page_params = {**(params or {}), "startAt": start, "maxResults": PAGE_SIZE}
            return self.jira.get(resource_url, params=page_params)

        return self._fetch_pages(fetch_page, values_keys)

    @staticmethod
    def _fetch_pages(
        fetch_page: collections.abc.Callable[[int], object], values_key: str | tuple[str, ...]
    ) -> list[dict[str, typing.Any]]:
        results: list[dict[str, typing.Any]] = []
        start = 0
        while True:
            response = fetch_page(start)
            if not isinstance(response, dict):
                return results
            values_keys = (values_key,) if isinstance(values_key, str) else values_key
            page_values = next((response[key] for key in values_keys if key in response), [])
            if not isinstance(page_values, list):
                return results
            results.extend(value for value in page_values if isinstance(value, dict))
            if response.get("isLast") is True or not page_values:
                return results
            next_start = int(response.get("startAt", start)) + len(page_values)
            total = response.get("total")
            if total is not None and next_start >= int(total):
                return results
            if next_start <= start:
                return results
            start = next_start


def _escape_jql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
