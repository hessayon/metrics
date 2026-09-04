import pathlib

import pytest

from teammetrics.cli import create_parser, main


def test_parser_accepts_repeatable_emails_and_verbose() -> None:
    arguments = create_parser().parse_args(
        [
            "jira",
            "--from",
            "2026-08-01",
            "--to",
            "2026-08-31",
            "--email",
            "alice@example.com",
            "--email",
            "bob@example.com",
            "-v",
        ],
    )

    assert arguments.email == ["alice@example.com", "bob@example.com"]
    assert arguments.verbose is True


def test_rejects_missing_email() -> None:
    with pytest.raises(SystemExit) as raised_exit:
        create_parser().parse_args(["jira", "--from", "2026-08-01", "--to", "2026-08-31"])

    assert raised_exit.value.code == 2


@pytest.mark.parametrize(
    ("from_value", "to_value", "expected_message"),
    [
        ("20260801", "2026-08-31", "Error: Invalid date format. Use YYYY-MM-DD."),
        ("2026-09-01", "2026-08-31", "Error: --from must be on or before --to"),
    ],
)
def test_reports_date_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    from_value: str,
    to_value: str,
    expected_message: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        ["jira", "--from", from_value, "--to", to_value, "--email", "alice@example.com"],
    )

    assert exit_code == 1
    assert capsys.readouterr().err.strip() == expected_message


def test_reports_missing_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        ["bitbucket", "--from", "2026-08-01", "--to", "2026-08-31", "--email", "alice@example.com"],
    )

    assert exit_code == 1
    assert capsys.readouterr().err.strip() == "Error: .env file not found"
