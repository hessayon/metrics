import json
import os
import pathlib
import time
import typing

import pytest

import teammetrics.bitbucket_client
import teammetrics.jira_client
from teammetrics.cli import main


@pytest.fixture
def cli_timezone(monkeypatch: pytest.MonkeyPatch) -> typing.Iterator[None]:
    original_timezone = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Etc/GMT+12")
    time.tzset()
    yield
    if original_timezone is None:
        monkeypatch.delenv("TZ", raising=False)
    else:
        monkeypatch.setenv("TZ", original_timezone)
    time.tzset()


class JiraFixture:
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.jql_starts: list[int] = []
        self.changelog_starts: list[int] = []

    def get_project(self, project: str) -> dict[str, str]:
        return {"key": project}

    def user_find_by_user_string(self, *, username: str, limit: int) -> list[dict[str, str]]:
        del limit
        return [{"emailAddress": username}]

    def get_all_fields(self) -> list[dict[str, str]]:
        return [{"id": "customfield_42", "name": "Story Points"}]

    def jql(self, query: str, *, fields: list[str], start: int, limit: int) -> dict[str, typing.Any]:
        del fields, limit
        self.jql_starts.append(start)
        created_dates = (
            "2026-08-02T02:00:00+14:00",
            "2026-08-15T12:00:00+14:00",
            "2026-09-02T02:00:00+14:00",
        )
        points = (5, 3, 13)
        issue = {
            "key": f"CI-{start + 1}",
            "fields": {"created": created_dates[start], "customfield_42": points[start]},
        }
        assert "assignee" in query or "reporter" in query
        return {"startAt": start, "total": 3, "issues": [issue]}

    def resource_url(self, resource: str) -> str:
        return resource

    def get(self, resource: str, *, params: dict[str, typing.Any]) -> dict[str, typing.Any]:
        if resource.startswith("issue/"):
            start = int(params["startAt"])
            self.changelog_starts.append(start)
            issue_number = int(resource.split("-")[1].split("/", maxsplit=1)[0])
            deliveries = (
                "2026-08-02T02:00:00+14:00",
                "2026-08-15T12:00:00+14:00",
                "2026-09-02T02:00:00+14:00",
            )
            history = (
                {"created": "2026-08-02T01:00:00+14:00", "items": [{"field": "status", "toString": "In Progress"}]}
                if start == 0
                else {
                    "created": deliveries[issue_number - 1],
                    "items": [{"field": "status", "toString": "Ready For IFT"}],
                }
            )
            return {"startAt": start, "total": 2, "values": [history]}
        raise RuntimeError("Agile API unavailable")

    def get_all_agile_boards(self, **kwargs: object) -> typing.NoReturn:
        del kwargs
        raise RuntimeError("Agile API unavailable")

    def get_agile_resource_url(self, resource: str, *, legacy_api: bool) -> str:
        del legacy_api
        return resource


@pytest.fixture
def jira_fixture(monkeypatch: pytest.MonkeyPatch) -> JiraFixture:
    fixture = JiraFixture()

    def build_jira(**kwargs: object) -> JiraFixture:
        del kwargs
        return fixture

    monkeypatch.setattr(teammetrics.jira_client, "Jira", build_jira)
    return fixture


def test_jira_command_integration_paginates_filters_boundaries_and_keeps_all_links(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    cli_timezone: None,
    jira_fixture: JiraFixture,
) -> None:
    del cli_timezone
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "JIRA_URL=https://jira.example.com\nJIRA_TOKEN=token\nJIRA_PROJECT=CI\n",
        encoding="utf-8",
    )

    exit_code = main([
        "jira", "--from", "2026-08-01", "--to", "2026-08-31", "--email", "alice@example.com",
    ])

    report = json.loads(capsys.readouterr().out)[0]
    assert exit_code == 0
    assert jira_fixture.jql_starts == [0, 1, 2, 0, 1, 2]
    assert jira_fixture.changelog_starts == [0, 1, 0, 1, 0, 1]
    assert report["metrics"]["stories_delivered"] == 2
    assert report["metrics"]["stories_created"] == 2
    assert [story["key"] for story in report["links"]["delivered_stories"]] == ["CI-1", "CI-2"]
    assert [story["key"] for story in report["links"]["created_stories"]] == ["CI-1", "CI-2"]


class BitbucketFixture:
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.repositories_seen: list[str] = []

    def project(self, project: str) -> dict[str, str]:
        return {"key": project}

    def get_users(self, *, user_filter: str, limit: int, start: int) -> dict[str, list[dict[str, str]]]:
        del limit, start
        return {"values": [{"emailAddress": user_filter}]}

    def repo_list(self, project: str, *, limit: None) -> typing.Iterator[dict[str, str]]:
        del project, limit
        yield {"slug": "core"}
        yield {"slug": "web"}

    def get_pull_requests(
        self,
        project: str,
        repository: str,
        *,
        state: str,
        limit: None,
    ) -> typing.Iterator[dict[str, typing.Any]]:
        del project, state, limit
        self.repositories_seen.append(repository)
        identifiers = (1, 2) if repository == "core" else (3,)
        for identifier in identifiers:
            yield {
                "id": identifier,
                "createdDate": "2026-08-01T00:00:00+14:00",
                "author": {"user": {"emailAddress": "alice@example.com"}},
                "reviewers": [{"user": {"emailAddress": "bob@example.com"}}],
            }

    def get_pull_requests_activities(
        self,
        project: str,
        repository: str,
        identifier: int,
        *,
        limit: None,
    ) -> typing.Iterator[dict[str, typing.Any]]:
        del project, repository, limit
        merged_dates = {
            1: "2026-08-02T02:00:00+14:00",
            2: "2026-08-15T12:00:00+14:00",
            3: "2026-09-02T02:00:00+14:00",
        }
        yield {"action": "MERGED", "createdDate": merged_dates[identifier]}


@pytest.fixture
def bitbucket_fixture(monkeypatch: pytest.MonkeyPatch) -> BitbucketFixture:
    fixture = BitbucketFixture()

    def build_bitbucket(**kwargs: object) -> BitbucketFixture:
        del kwargs
        return fixture

    monkeypatch.setattr(teammetrics.bitbucket_client, "Bitbucket", build_bitbucket)
    return fixture


def test_bitbucket_command_integration_paginates_filters_boundaries_and_keeps_all_links(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    cli_timezone: None,
    bitbucket_fixture: BitbucketFixture,
) -> None:
    del cli_timezone
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "BITBUCKET_URL=https://bb.example.com\nBITBUCKET_TOKEN=token\nBITBUCKET_PROJECT=CI\n",
        encoding="utf-8",
    )

    exit_code = main([
        "bitbucket", "--from", "2026-08-01", "--to", "2026-08-31", "--email", "alice@example.com",
    ])

    report = json.loads(capsys.readouterr().out)[0]
    assert exit_code == 0
    assert bitbucket_fixture.repositories_seen == ["core", "web"]
    assert report["metrics"]["total_merged_prs"] == 2
    assert report["links"]["merged_prs"] == [
        {"id": 1, "url": "https://bb.example.com/projects/CI/repos/core/pull-requests/1"},
        {"id": 2, "url": "https://bb.example.com/projects/CI/repos/core/pull-requests/2"},
    ]
