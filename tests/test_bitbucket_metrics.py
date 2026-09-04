import dataclasses
import datetime

from teammetrics.bitbucket_client import PullRequest, PullRequestComment
from teammetrics.bitbucket_metrics import calculate_bitbucket_metrics
from teammetrics.period import build_period


def _timestamp(day: int, hour: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 8, day, hour, tzinfo=datetime.UTC).astimezone()


def _pull_request(
    identifier: int,
    repository_slug: str,
    author_email: str,
    reviewer_emails: frozenset[str],
    comments: tuple[PullRequestComment, ...],
) -> PullRequest:
    return PullRequest(
        identifier=identifier,
        repository_slug=repository_slug,
        author_email=author_email,
        reviewer_emails=reviewer_emails,
        created_at=_timestamp(1),
        merged_at=_timestamp(20),
        url=f"https://bb.example.com/pr/{identifier}",
        comments=comments,
    )


def test_calculates_authored_prs_review_comments_turnaround_and_complete_links() -> None:
    pull_requests = (
        _pull_request(
            1,
            "core",
            "alice@example.com",
            frozenset({"bob@example.com"}),
            (
                PullRequestComment(author_email="outsider@example.com", created_at=_timestamp(1, 1)),
                PullRequestComment(author_email="bob@example.com", created_at=_timestamp(2)),
            ),
        ),
        _pull_request(
            2,
            "core",
            "alice@example.com",
            frozenset({"carol@example.com"}),
            (PullRequestComment(author_email="carol@example.com", created_at=_timestamp(3)),),
        ),
        _pull_request(
            3,
            "web",
            "bob@example.com",
            frozenset({"alice@example.com"}),
            (
                PullRequestComment(author_email="alice@example.com", created_at=_timestamp(4)),
                PullRequestComment(author_email="alice@example.com", created_at=_timestamp(31)),
            ),
        ),
    )

    metrics, links = calculate_bitbucket_metrics(
        "Alice@Example.com",
        pull_requests,
        build_period("2026-08-01", "2026-08-30"),
    )

    assert metrics == {
        "total_merged_prs": 2,
        "prs_by_repo": {"core": 2},
        "review_comments": 1,
        "average_pr_turnaround_hours": 36.0,
    }
    assert links == {
        "merged_prs": [
            {"id": 1, "url": "https://bb.example.com/pr/1"},
            {"id": 2, "url": "https://bb.example.com/pr/2"},
        ],
    }


def test_returns_empty_defaults_and_ignores_author_and_non_reviewer_comments() -> None:
    pull_request = _pull_request(
        4,
        "web",
        "alice@example.com",
        frozenset({"bob@example.com"}),
        (
            PullRequestComment(author_email="alice@example.com", created_at=_timestamp(2)),
            PullRequestComment(author_email="outsider@example.com", created_at=_timestamp(3)),
        ),
    )

    metrics, links = calculate_bitbucket_metrics(
        "nobody@example.com",
        (pull_request,),
        build_period("2026-08-01", "2026-08-31"),
    )

    assert metrics == {
        "total_merged_prs": 0,
        "prs_by_repo": {},
        "review_comments": 0,
        "average_pr_turnaround_hours": None,
    }
    assert links == {"merged_prs": []}


def test_ignores_pull_requests_merged_outside_period() -> None:
    pull_request = _pull_request(
        5,
        "web",
        "alice@example.com",
        frozenset({"bob@example.com"}),
        (PullRequestComment(author_email="bob@example.com", created_at=_timestamp(2)),),
    )

    metrics, links = calculate_bitbucket_metrics(
        "alice@example.com",
        (dataclasses.replace(pull_request, merged_at=_timestamp(20)),),
        build_period("2026-08-01", "2026-08-19"),
    )

    assert metrics["total_merged_prs"] == 0
    assert metrics["average_pr_turnaround_hours"] is None
    assert links == {"merged_prs": []}
