import argparse
import collections.abc
import sys
import typing

from teammetrics.bitbucket_client import BitbucketClient
from teammetrics.bitbucket_metrics import calculate_bitbucket_metrics
from teammetrics.config import ServiceConfig, ServiceName, load_config
from teammetrics.jira_client import JiraClient
from teammetrics.jira_metrics import build_jira_metrics
from teammetrics.output import write_reports
from teammetrics.period import Period, build_period


class EmployeeLookup(typing.Protocol):
    def employee_exists(self, email: str) -> bool: ...


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teammetrics")
    subparsers = parser.add_subparsers(dest="service", required=True)
    for service_name in ("jira", "bitbucket"):
        service_parser = subparsers.add_parser(service_name)
        service_parser.add_argument("--from", dest="from_value", required=True, metavar="YYYY-MM-DD")
        service_parser.add_argument("--to", dest="to_value", required=True, metavar="YYYY-MM-DD")
        service_parser.add_argument("--email", action="append", required=True)
        service_parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(arguments: collections.abc.Sequence[str] | None = None) -> int:
    parsed_arguments = create_parser().parse_args(arguments)
    try:
        period = build_period(parsed_arguments.from_value, parsed_arguments.to_value)
        config = load_config(typing_service_name(parsed_arguments.service))
        reports = (
            _build_jira_reports(config, period, parsed_arguments.email, verbose=parsed_arguments.verbose)
            if parsed_arguments.service == "jira"
            else _build_bitbucket_reports(config, period, parsed_arguments.email, verbose=parsed_arguments.verbose)
        )
        write_reports(reports)
    except Exception as error:  # noqa: BLE001 - the CLI must turn remote client failures into documented errors
        sys.stderr.write(f"Error: {error}\n")
        return 1
    return 0


def _build_jira_reports(
    config: ServiceConfig,
    period: Period,
    emails: list[str],
    *,
    verbose: bool,
) -> list[dict[str, typing.Any]]:
    client = JiraClient(config)
    if not client.project_exists():
        raise ValueError(f"Jira project '{config.project}' not found")
    _validate_employees(client, emails, "Jira")
    story_points_field = client.discover_story_points_field()
    sprints = client.fetch_scrum_sprints()
    reports = []
    for email in emails:
        _log_progress(verbose, f"Fetching stories for {email}")
        assigned_stories = client.attach_complete_changelogs(
            client.fetch_assigned_story_candidates(email, period, story_points_field)
        )
        created_stories = client.fetch_created_story_candidates(email, period, story_points_field)
        report = build_jira_metrics(
            assigned_stories,
            created_stories,
            sprints,
            period,
            story_points_field,
            config.url,
        )
        reports.append(_employee_report(email, period, report["metrics"], report["links"]))
    return reports


def _build_bitbucket_reports(
    config: ServiceConfig,
    period: Period,
    emails: list[str],
    *,
    verbose: bool,
) -> list[dict[str, typing.Any]]:
    client = BitbucketClient(url=config.url, token=config.token, project=config.project)
    client.validate_project()
    _validate_employees(client, emails, "Bitbucket")
    _log_progress(verbose, "Fetching merged pull requests")
    pull_requests = client.fetch_merged_pull_requests(period)
    reports = []
    for email in emails:
        metrics, links = calculate_bitbucket_metrics(email, pull_requests, period)
        reports.append(_employee_report(email, period, metrics, links))
    return reports


def _validate_employees(client: EmployeeLookup, emails: list[str], service_label: str) -> None:
    missing_emails = [email for email in emails if not client.employee_exists(email)]
    if missing_emails:
        raise ValueError(f"Employees not found in {service_label}: {', '.join(missing_emails)}")


def _employee_report(
    email: str,
    period: Period,
    metrics: dict[str, typing.Any],
    links: dict[str, typing.Any],
) -> dict[str, typing.Any]:
    return {
        "email": email,
        "period": {"from": period.from_date.isoformat(), "to": period.to_date.isoformat()},
        "metrics": metrics,
        "links": links,
    }


def _log_progress(verbose: bool, message: str) -> None:
    if verbose:
        sys.stderr.write(f"{message}\n")


def typing_service_name(service_name: str) -> ServiceName:
    if service_name == "jira":
        return "jira"
    return "bitbucket"
