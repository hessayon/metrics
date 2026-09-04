import datetime
import typing

import pytest
import requests

from teammetrics.bitbucket_client import BitbucketClient
from teammetrics.period import build_period


class FakeBitbucket:
    def __init__(self) -> None:
        self.activity_calls: list[tuple[str, str, int, int | None]] = []

    def project(self, project: str) -> dict[str, str]:
        return {"key": project} if project == "CI" else {}

    def get_users(self, *, user_filter: str, limit: int, start: int) -> dict[str, typing.Any]:
        del limit, start
        if user_filter == "alice@example.com":
            return {"values": [{"emailAddress": "Alice@Example.com"}]}
        return {"values": []}

    def repo_list(self, project: str, *, limit: None) -> typing.Iterator[dict[str, str]]:
        assert project == "CI"
        assert limit is None
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
        assert (project, state, limit) == ("CI", "MERGED", None)
        if repository == "core":
            yield _pull_request(7, "alice@example.com", created_date=1_786_080_000_000)
            yield _pull_request(8, "alice@example.com", created_date=1_786_080_000_000)

    def get_pull_requests_activities(
        self,
        project: str,
        repository: str,
        identifier: int,
        *,
        limit: None,
    ) -> typing.Iterator[dict[str, typing.Any]]:
        self.activity_calls.append((project, repository, identifier, limit))
        if identifier == 7:
            yield {"action": "MERGED", "createdDate": 1_786_168_800_000}
            yield {
                "action": "COMMENTED",
                "createdDate": 1_786_123_200_000,
                "comment": {"author": {"emailAddress": "Bob@Example.com"}, "createdDate": 1_786_123_200_000},
            }
        else:
            yield {"action": "MERGED", "createdDate": 1_788_760_800_000}


def _pull_request(identifier: int, author_email: str, *, created_date: int) -> dict[str, typing.Any]:
    return {
        "id": identifier,
        "uuid": "must-not-be-used",
        "createdDate": created_date,
        "author": {"user": {"emailAddress": author_email}},
        "reviewers": [{"user": {"emailAddress": "bob@example.com"}}],
    }


def test_validates_project_and_employee_by_exact_case_insensitive_email() -> None:
    bitbucket_api = FakeBitbucket()
    client = BitbucketClient(url="https://bb.example.com/", token="token", project="CI", bitbucket_api=bitbucket_api)

    client.validate_project()

    assert client.employee_exists("alice@example.com")
    assert not client.employee_exists("missing@example.com")


def test_reports_missing_project() -> None:
    client = BitbucketClient(url="https://bb.example.com", token="token", project="NOPE", bitbucket_api=FakeBitbucket())

    with pytest.raises(ValueError, match="Bitbucket project 'NOPE' not found"):
        client.validate_project()


@pytest.mark.parametrize(("status_code", "expected_error"), [(404, ValueError), (500, requests.HTTPError)])
def test_maps_only_project_not_found_http_error(status_code: int, expected_error: type[Exception]) -> None:
    bitbucket_api = FakeBitbucket()
    response = requests.Response()
    response.status_code = status_code
    bitbucket_api.project = lambda _project: (_ for _ in ()).throw(requests.HTTPError(response=response))
    client = BitbucketClient(url="https://bb.example.com", token="token", project="CI", bitbucket_api=bitbucket_api)

    with pytest.raises(expected_error):
        client.validate_project()


def test_searches_all_user_pages_for_exact_email() -> None:
    bitbucket_api = FakeBitbucket()
    user_calls: list[int] = []

    def get_users(*, user_filter: str, limit: int, start: int) -> dict[str, typing.Any]:
        del user_filter, limit
        user_calls.append(start)
        if start == 0:
            return {
                "values": [{"emailAddress": "not-alice@example.com"}],
                "isLastPage": False,
                "nextPageStart": 25,
            }
        return {"values": [{"emailAddress": "Alice@Example.com"}], "isLastPage": True}

    bitbucket_api.get_users = get_users
    client = BitbucketClient(url="https://bb.example.com", token="token", project="CI", bitbucket_api=bitbucket_api)

    assert client.employee_exists("alice@example.com")
    assert user_calls == [0, 25]


def test_fetches_every_repository_and_uses_merged_activity_timestamp() -> None:
    bitbucket_api = FakeBitbucket()
    client = BitbucketClient(url="https://bb.example.com/", token="token", project="CI", bitbucket_api=bitbucket_api)

    pull_requests = client.fetch_merged_pull_requests(build_period("2026-08-01", "2026-08-31"))

    assert len(pull_requests) == 1
    assert pull_requests[0].identifier == 7
    assert pull_requests[0].repository_slug == "core"
    assert pull_requests[0].author_email == "alice@example.com"
    assert pull_requests[0].reviewer_emails == frozenset({"bob@example.com"})
    assert pull_requests[0].comments[0].author_email == "bob@example.com"
    assert pull_requests[0].url == "https://bb.example.com/projects/CI/repos/core/pull-requests/7"
    assert pull_requests[0].merged_at == datetime.datetime.fromtimestamp(1_786_168_800, tz=datetime.UTC).astimezone()
    assert bitbucket_api.activity_calls == [("CI", "core", 7, None), ("CI", "core", 8, None)]
