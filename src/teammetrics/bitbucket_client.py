import dataclasses
import datetime
import typing

import requests
from atlassian import Bitbucket

from teammetrics.period import Period


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class PullRequestComment:
    author_email: str | None
    created_at: datetime.datetime


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class PullRequest:
    identifier: int
    repository_slug: str
    author_email: str | None
    reviewer_emails: frozenset[str]
    created_at: datetime.datetime
    merged_at: datetime.datetime
    url: str
    comments: tuple[PullRequestComment, ...]


@typing.final
class BitbucketClient:
    def __init__(
        self,
        *,
        url: str,
        token: str,
        project: str,
        bitbucket_api: Bitbucket | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.project = project
        self._api = bitbucket_api or Bitbucket(url=self.url, token=token, cloud=False)

    def validate_project(self) -> None:
        try:
            project = self._api.project(self.project)
        except requests.HTTPError as error:
            if error.response is None or error.response.status_code != requests.codes.not_found:
                raise
            raise ValueError(f"Bitbucket project '{self.project}' not found") from error
        if not project:
            raise ValueError(f"Bitbucket project '{self.project}' not found")

    def employee_exists(self, email: str) -> bool:
        start = 0
        while True:
            response = self._api.get_users(user_filter=email, limit=100, start=start)
            if any(_email(user) == email.casefold() for user in response.get("values", ())):
                return True
            if response.get("isLastPage", True):
                return False
            start = int(response["nextPageStart"])

    def fetch_merged_pull_requests(self, period: Period) -> tuple[PullRequest, ...]:
        pull_requests: list[PullRequest] = []
        for repository in self._api.repo_list(self.project, limit=None):
            repository_slug = str(repository["slug"])
            for raw_pull_request in self._api.get_pull_requests(
                self.project,
                repository_slug,
                state="MERGED",
                limit=None,
            ):
                activities = tuple(
                    self._api.get_pull_requests_activities(
                        self.project,
                        repository_slug,
                        raw_pull_request["id"],
                        limit=None,
                    ),
                )
                merged_dates = [
                    _timestamp(activity["createdDate"])
                    for activity in activities
                    if activity.get("action") == "MERGED" and "createdDate" in activity
                ]
                if not merged_dates or not period.contains(merged_dates[0]):
                    continue
                pull_requests.append(
                    self._build_pull_request(
                        raw_pull_request,
                        activities,
                        repository_slug=repository_slug,
                        merged_at=merged_dates[0],
                    ),
                )
        return tuple(pull_requests)

    def _build_pull_request(
        self,
        raw_pull_request: dict[str, typing.Any],
        activities: tuple[dict[str, typing.Any], ...],
        *,
        repository_slug: str,
        merged_at: datetime.datetime,
    ) -> PullRequest:
        identifier = int(raw_pull_request["id"])
        return PullRequest(
            identifier=identifier,
            repository_slug=repository_slug,
            author_email=_email(raw_pull_request.get("author", {}).get("user", {})),
            reviewer_emails=frozenset(
                email
                for reviewer in raw_pull_request.get("reviewers", ())
                if (email := _email(reviewer.get("user", {}))) is not None
            ),
            created_at=_timestamp(raw_pull_request["createdDate"]),
            merged_at=merged_at,
            url=f"{self.url}/projects/{self.project}/repos/{repository_slug}/pull-requests/{identifier}",
            comments=tuple(
                PullRequestComment(
                    author_email=_email(activity["comment"].get("author", {})),
                    created_at=_timestamp(activity["comment"].get("createdDate", activity["createdDate"])),
                )
                for activity in activities
                if activity.get("action") == "COMMENTED" and isinstance(activity.get("comment"), dict)
            ),
        )


def _email(user: dict[str, typing.Any]) -> str | None:
    email = user.get("emailAddress")
    return email.casefold() if isinstance(email, str) else None


def _timestamp(value: str | float) -> datetime.datetime:
    if isinstance(value, str):
        parsed_timestamp = datetime.datetime.fromisoformat(value)
    else:
        parsed_timestamp = datetime.datetime.fromtimestamp(value / 1000, tz=datetime.UTC)
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise ValueError("API timestamp must include a timezone")
    return parsed_timestamp.astimezone()
