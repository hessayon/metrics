import collections
import typing

from teammetrics.bitbucket_client import PullRequest, PullRequestComment
from teammetrics.period import Period


def calculate_bitbucket_metrics(
    email: str,
    pull_requests: typing.Iterable[PullRequest],
    period: Period,
) -> tuple[dict[str, typing.Any], dict[str, list[dict[str, int | str]]]]:
    employee_email = email.casefold()
    pull_request_list = tuple(pull_request for pull_request in pull_requests if period.contains(pull_request.merged_at))
    authored_pull_requests = tuple(
        pull_request for pull_request in pull_request_list if pull_request.author_email == employee_email
    )
    repository_counts = collections.Counter(pull_request.repository_slug for pull_request in authored_pull_requests)
    review_comments = sum(
        1
        for pull_request in pull_request_list
        if employee_email in pull_request.reviewer_emails
        for comment in pull_request.comments
        if comment.author_email == employee_email and period.contains(comment.created_at)
    )
    turnaround_hours = [
        (review_comment.created_at - pull_request.created_at).total_seconds() / 3600
        for pull_request in authored_pull_requests
        if (review_comment := _first_reviewer_comment(pull_request)) is not None
    ]
    metrics: dict[str, typing.Any] = {
        "total_merged_prs": len(authored_pull_requests),
        "prs_by_repo": dict(repository_counts),
        "review_comments": review_comments,
        "average_pr_turnaround_hours": (
            round(sum(turnaround_hours) / len(turnaround_hours), 1) if turnaround_hours else None
        ),
    }
    links = {
        "merged_prs": [
            {"id": pull_request.identifier, "url": pull_request.url} for pull_request in authored_pull_requests
        ],
    }
    return metrics, links


def _first_reviewer_comment(pull_request: PullRequest) -> PullRequestComment | None:
    valid_comments = (
        comment
        for comment in pull_request.comments
        if comment.author_email != pull_request.author_email
        and comment.author_email in pull_request.reviewer_emails
        and comment.created_at >= pull_request.created_at
    )
    return min(valid_comments, key=lambda comment: comment.created_at, default=None)
