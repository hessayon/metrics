import pathlib

import pytest

from teammetrics.config import ServiceConfig, load_config


def test_loads_only_selected_service(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "JIRA_URL=https://jira.example\nJIRA_TOKEN=secret\nJIRA_PROJECT=TEAM\n",
        encoding="utf-8",
    )

    assert load_config("jira") == ServiceConfig(url="https://jira.example", token="secret", project="TEAM")


def test_reports_missing_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=r"^\.env file not found$"):
        load_config("bitbucket")


def test_lists_all_empty_selected_service_values(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("BITBUCKET_URL=\nBITBUCKET_TOKEN=token\n", encoding="utf-8")

    with pytest.raises(ValueError, match="BITBUCKET_URL, BITBUCKET_PROJECT"):
        load_config("bitbucket")
