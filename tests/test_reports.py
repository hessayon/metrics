import json
import pathlib

import pytest

import teammetrics.cli
from teammetrics.cli import main


class MissingEmployeeClient:
    fetched = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def project_exists(self) -> bool:
        return True

    def validate_project(self) -> None:
        return None

    def employee_exists(self, email: str) -> bool:
        return email == "present@example.com"

    def discover_story_points_field(self) -> str:
        self.fetched = True
        return "customfield_1"

    def fetch_merged_pull_requests(self, period: object) -> tuple[()]:
        del period
        self.fetched = True
        return ()


@pytest.mark.parametrize(("service", "label"), [("jira", "Jira"), ("bitbucket", "Bitbucket")])
def test_collects_all_missing_employees_before_fetching(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    service: str,
    label: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"{service.upper()}_URL=https://example.com\n{service.upper()}_TOKEN=token\n"
        f"{service.upper()}_PROJECT=CI\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(teammetrics.cli, f"{label}Client", MissingEmployeeClient)

    exit_code = main([
        service,
        "--from",
        "2026-08-01",
        "--to",
        "2026-08-31",
        "--email",
        "missing-one@example.com",
        "--email",
        "present@example.com",
        "--email",
        "missing-two@example.com",
    ])

    assert exit_code == 1
    assert capsys.readouterr().err.strip() == (
        f"Error: Employees not found in {label}: missing-one@example.com, missing-two@example.com"
    )


class FakeBitbucketClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def validate_project(self) -> None:
        return None

    def employee_exists(self, email: str) -> bool:
        return email == "alice@example.com"

    def fetch_merged_pull_requests(self, period: object) -> tuple[()]:
        del period
        return ()


def test_bitbucket_command_emits_one_service_specific_array(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "BITBUCKET_URL=https://bb.example.com\nBITBUCKET_TOKEN=token\nBITBUCKET_PROJECT=CI\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(teammetrics.cli, "BitbucketClient", FakeBitbucketClient)
    monkeypatch.setattr(teammetrics.cli, "JiraClient", None)

    exit_code = main([
        "bitbucket",
        "--from",
        "2026-08-01",
        "--to",
        "2026-08-31",
        "--email",
        "alice@example.com",
    ])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output == [{
        "email": "alice@example.com",
        "period": {"from": "2026-08-01", "to": "2026-08-31"},
        "metrics": {
            "total_merged_prs": 0,
            "prs_by_repo": {},
            "review_comments": 0,
            "average_pr_turnaround_hours": None,
        },
        "links": {"merged_prs": []},
    }]
