# TeamMetrics

TeamMetrics produces per-employee JSON reports from Jira Data Center or Bitbucket Data Center. It requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

## Setup

```bash
cp .env.example .env
uv sync
```

Fill in the service you intend to use:

```dotenv
JIRA_URL=https://jira.company.com
JIRA_TOKEN=your-bearer-token
JIRA_PROJECT=CI

BITBUCKET_URL=https://bb.company.com
BITBUCKET_TOKEN=your-bearer-token
BITBUCKET_PROJECT=CI
```

Each command reads `.env` from the current directory and validates only its selected service. Jira values are not required for the `bitbucket` command, and Bitbucket values are not required for the `jira` command. Both services use Bearer-token authentication.

## Usage

```bash
uv run python -m teammetrics jira \
  --from 2026-08-01 --to 2026-08-31 \
  --email alice@company.com

uv run python -m teammetrics bitbucket \
  --from 2026-08-01 --to 2026-08-31 \
  --email alice@company.com --email bob@company.com
```

Add `--verbose` or `-v` to send progress messages to stderr. JSON is always written to stdout as an array, even for one employee.

Dates use the machine's local timezone. The requested dates are inclusive and are evaluated as the half-open interval from midnight on `--from` through, but excluding, midnight after `--to`. API timestamps are converted to that timezone before filtering.

## Jira output

```json
[
  {
    "email": "alice@company.com",
    "period": {"from": "2026-08-01", "to": "2026-08-31"},
    "metrics": {
      "total_story_points": 8,
      "stories_delivered": 2,
      "stories_created": 1,
      "stories_carried_over": 1,
      "carry_over_percentage": 50.0,
      "average_cycle_time_days": 4.5,
      "average_sp_per_sprint": 4.0
    },
    "links": {
      "delivered_stories": [
        {"key": "CI-123", "url": "https://jira.company.com/browse/CI-123", "points": 5},
        {"key": "CI-124", "url": "https://jira.company.com/browse/CI-124", "points": 3}
      ],
      "created_stories": [
        {"key": "CI-125", "url": "https://jira.company.com/browse/CI-125", "points": 3}
      ]
    }
  }
]
```

## Bitbucket output

```json
[
  {
    "email": "alice@company.com",
    "period": {"from": "2026-08-01", "to": "2026-08-31"},
    "metrics": {
      "total_merged_prs": 2,
      "prs_by_repo": {"core": 2},
      "review_comments": 4,
      "average_pr_turnaround_hours": 18.5
    },
    "links": {
      "merged_prs": [
        {"id": 42, "url": "https://bb.company.com/projects/CI/repos/core/pull-requests/42"},
        {"id": 43, "url": "https://bb.company.com/projects/CI/repos/core/pull-requests/43"}
      ]
    }
  }
]
```
