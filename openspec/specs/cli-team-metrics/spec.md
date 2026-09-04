# Spec: CLI Team Metrics Tool

> **Purpose:** CLI utility for team leads to collect and analyze team member metrics from Jira and Bitbucket Data Center.
>
> **Input:** `.env` file with connection details and one project per service, `--from` and `--to` dates, list of employee emails.
>
> **Output:** Service-specific JSON arrays of per-employee Jira or Bitbucket metric reports with complete resource lists.

## Requirements

### REQ-1: Configuration

The tool reads authentication and connection details from `Path.cwd() / ".env"`. Both services use Bearer-token authentication only.

**Required `.env` variables:**

| Variable | Description | Example |
|---|---|---|
| `JIRA_URL` | Base URL of self-hosted Jira Data Center | `https://jira.company.com` |
| `JIRA_TOKEN` | Authentication token for Jira API | `gqltn...` |
| `JIRA_PROJECT` | Jira project key used by the `jira` command | `CI` |
| `BITBUCKET_URL` | Base URL of self-hosted Bitbucket Data Center | `https://bb.company.com` |
| `BITBUCKET_TOKEN` | Personal access token for Bitbucket API | `bbpat...` |
| `BITBUCKET_PROJECT` | Bitbucket project key used by the `bitbucket` command | `CI` |

A `.env.example` file in the project root provides a template.

**Acceptance criteria:**
- AC1: Tool exits with a clear error message if `.env` is missing or any variable required by the selected command is empty. `jira` requires the three `JIRA_*` variables; `bitbucket` requires the three `BITBUCKET_*` variables.
- AC2: Tool exits with code 1 and message `Error: .env file not found` if `.env` does not exist.
- AC3: Missing `.env` variables produce an error listing all missing keys.
- AC4: Tokens are sent as `Authorization: Bearer <token>`; Basic-auth fallback is not supported.

### REQ-2: CLI Interface

The tool is run via one of two independent subcommands. Each command accesses only its own service and emits only that service's metrics.

**Usage:**
```
python -m teammetrics jira --from YYYY-MM-DD --to YYYY-MM-DD --email EMAIL [--email EMAIL ...]
python -m teammetrics bitbucket --from YYYY-MM-DD --to YYYY-MM-DD --email EMAIL [--email EMAIL ...]
```

**Arguments:**
| Argument | Required | Description |
|---|---|---|
| `--from` | Yes | Start date (inclusive), format `YYYY-MM-DD` |
| `--to` | Yes | End date (inclusive), format `YYYY-MM-DD` |
| `--email` | Yes (at least one) | Employee email, can be specified multiple times |
| `--verbose` / `-v` | No | Log progress to stderr |

**Acceptance criteria:**
- AC1: `--from` and `--to` are validated as `YYYY-MM-DD` format. Invalid format → error.
- AC2: At least one `--email` is required. Zero `--email` → error.
- AC3: `--verbose` flag writes progress messages to stderr (e.g., `Fetching stories for alice@...`).
- AC4: `--help` prints usage information (provided by argparse automatically).
- AC5: Date boundaries are interpreted in the local timezone of the machine running the CLI. Implement the inclusive user-facing range as the half-open interval `[<from> 00:00, <day-after-to> 00:00)`; API timestamps are converted to the machine's local timezone before comparison.
- AC6: `--from` later than `--to` exits with code 1 and message `Error: --from must be on or before --to`.

### REQ-3: Story Points Collected

Total story points for stories assigned to the employee where the story reached `Ready For IFT` status within the specified period.

**Calculation:**
- Query candidate stories in `JIRA_PROJECT` assigned to the employee, widening any date-only JQL bound by two calendar days at each edge because Jira evaluates those bounds in the Jira server timezone. Then inspect their changelogs and authoritatively filter transition timestamps against the CLI-local half-open period. If there are multiple transitions to `Ready For IFT` in the period, use the first as the delivery event.
- Discover the Jira REST field ID by loading field metadata and matching the exact field name `Story Points`. The REST ID is installation-specific (typically `customfield_<id>`).
- Sum the discovered Story Points field for all delivered stories.

**JSON field:**
```json
"total_story_points": 42
```

**Acceptance criteria:**
- AC1: A story counts when its changelog contains a transition to `Ready For IFT` during the period; its current status and `updated` timestamp do not determine delivery.
- AC2: An unset Story Points field contributes 0.
- AC3: If no stories found → `0`.
- AC4: The tool exits with a clear error if no field named `Story Points` exists or if more than one field has that exact name.

### REQ-4: Stories Delivered

Count of stories assigned to the employee that reached `Ready For IFT` status within the period.

**JSON field:**
```json
"stories_delivered": 10
```

**Acceptance criteria:**
- AC1: Uses the same project, assignee, and changelog transition filter as REQ-3, but counts instead of summing.
- AC2: If no stories found → `0`.

### REQ-5: Stories Created

Count of stories created by the employee within the period.

**Coarse candidate JQL:**
```
project = <JIRA_PROJECT> AND issuetype = Story AND reporter = <email> AND created >= "<day-before-from>" AND created < "<day-after-day-after-to>"
```

Jira evaluates date-only JQL in its own timezone. Widen both edges by two calendar days for candidate retrieval; convert every returned `created` timestamp to the CLI machine's local timezone and keep it only when it falls in `[from 00:00, day-after-to 00:00)`.

**JSON field:**
```json
"stories_created": 5
```

**Acceptance criteria:**
- AC1: Uses `reporter` field, not `assignee`.
- AC2: If no stories found → `0`.

### REQ-6: Stories Carried Over (Cross-Sprint)

Count and percentage of stories where work began in one Sprint but reached `Ready For IFT` in another.

**Calculation:**
1. Resolve all Jira boards for `JIRA_PROJECT`, keep Scrum boards, fetch their Sprints from the Jira Agile/GreenHopper API, and deduplicate Sprints by ID.
2. Keep Sprints with parseable `startDate` and `endDate` whose interval strictly intersects the requested period: `sprint.startDate < day-after-to` and `sprint.endDate > from`. Exclude Sprints without both parseable boundaries from period averages and event-time resolution.
3. For each delivered story (from REQ-3), use its first `Ready For IFT` transition in the period and the nearest preceding transition into `work started` or `in progress` as the work-cycle boundaries.
4. Process Sprint-field changelog items chronologically and reconstruct membership as a set of numeric Sprint IDs from each item's `from` and `to` values. At the work-start and `Ready For IFT` timestamps, intersect that membership with known Scrum Sprints satisfying `startDate <= event < endDate`. Exactly one match resolves the active Sprint; zero or multiple matches mean unknown.
5. A story is "carried over" when both Sprint IDs are known and differ. If either Sprint cannot be determined, the story is not counted as carried over.
6. Percentage = `(carried_over_count / stories_delivered) * 100`, rounded to 1 decimal.

**JSON fields:**
```json
"stories_carried_over": 2,
"carry_over_percentage": 15.4
```

**Acceptance criteria:**
- AC1: Uses the Jira Agile API (`/rest/agile/1.0/...` or `/rest/greenhopper/1.0/...` — fallback to the available endpoint on Data Center).
- AC2: If Agile API is unavailable → skip carry-over metrics, output `0` and `0.0`.
- AC3: If `stories_delivered` is `0` → `carry_over_percentage` is `0.0`.
- AC4: Boards are discovered from `JIRA_PROJECT`; no board ID is required in configuration.
- AC5: A Sprint returned by multiple boards is processed once.
- AC6: Kanban boards are ignored.
- AC7: Comparing the initial and final story Sprint is not sufficient; the comparison uses the Sprint at the selected work-start and delivery events.

### REQ-7: Merged Pull Requests

Count and breakdown of merged PRs per repository.

**Bitbucket query:**
- Query Bitbucket REST API for pull requests where:
  - repository belongs to `BITBUCKET_PROJECT`
  - `author` email matches the employee email
  - `status` is `MERGED`
  - merge timestamp is within the inclusive period
- Read each matching PR's activity stream to obtain the timestamp of its `MERGED` activity and its comments; this activity timestamp is the merge time. Do not substitute `closedDate` or `updated`.

**JSON fields:**
```json
"total_merged_prs": 8,
"prs_by_repo": {
  "ci-audit": 5,
  "ci-core": 3
}
```

**Acceptance criteria:**
- AC1: Only `MERGED` PRs are counted.
- AC2: `prs_by_repo` keys are repository slugs (not full paths).
- AC3: If no PRs found → `0` and `{}`.
- AC4: All repositories in `BITBUCKET_PROJECT` are queried.

### REQ-8: Review Comments

Count of comments written by the employee on PRs merged within the requested period where the employee is listed as a reviewer.

**Bitbucket query:**
- Query Bitbucket REST API for pull requests that belong to `BITBUCKET_PROJECT`, were merged within the requested period, and list the employee as a reviewer.
- Count only comments authored by that employee within the inclusive period.

**JSON field:**
```json
"review_comments": 12
```

**Acceptance criteria:**
- AC1: Reviewer and comment-author matching use the employee's email, which is the same in Jira and Bitbucket.
- AC2: Only comments on merged PRs count.
- AC3: If no reviews found → `0`.
- AC4: Comments written by other users do not count.
- AC5: Comments on PRs merged outside the requested period do not count.

### REQ-9: Average Cycle Time

Average time (in days) from when a story started work to when it reached `Ready For IFT`.

**Calculation:**
- For each delivered story, use the first `Ready For IFT` transition within the period that made the story delivered under REQ-3.
- Find the nearest preceding transition into `work started` or `in progress`; this is the start of the delivery cycle paired with that transition.
- Cycle time = `ift_timestamp - start_timestamp` in days (rounded to 1 decimal).
- Exclude stories for which no preceding work-start transition can be found, and average the remaining valid cycles.

**JSON field:**
```json
"average_cycle_time_days": 5.3
```

**Acceptance criteria:**
- AC1: Uses the Jira `changelog`; repeated work cycles are paired using the first `Ready For IFT` transition in the period and its nearest preceding work-start transition.
- AC2: If fewer than 2 stories have a valid start/delivery pair → `null` (not enough data).
- AC3: If no delivered stories or no valid pairs → `null`.

### REQ-10: Average Story Points per Sprint

Average story points delivered per Sprint across Sprints in the period.

**Calculation:**
1. Use deduplicated Sprints from Scrum boards whose intervals intersect the requested period.
2. Assign each delivered story to the Sprint active at its first `Ready For IFT` transition in the period. Stories whose Sprint cannot be determined are not assigned.
3. Sum story points per Sprint, including zero for an intersecting Sprint with no delivered stories.
4. Average across all intersecting Sprints.

**JSON field:**
```json
"average_sp_per_sprint": 14.0
```

**Acceptance criteria:**
- AC1: Uses Sprint grouping from the Agile API.
- AC2: If no Sprints in the period → `null`.
- AC3: Kanban boards are ignored.
- AC4: If the Agile API is unavailable → `null`.

### REQ-11: Average PR Turnaround Time

Average time (in hours) from PR creation to first review comment.

**Calculation:**
- For each merged PR authored by the employee under REQ-7, find the first comment written by a user listed as a reviewer of that PR.
- Turnaround = `first_comment_time - created_time` in hours (rounded to 1 decimal).
- Average across all qualifying PRs that have a valid reviewer comment.

**JSON field:**
```json
"average_pr_turnaround_hours": 18.5
```

**Acceptance criteria:**
- AC1: Only PRs with at least one valid reviewer comment are included.
- AC2: If no PRs have a valid reviewer comment → `null`.
- AC3: Comments by the PR author and by users not listed as reviewers are ignored.
- AC4: Only PRs merged within the requested period under REQ-7 are considered.

### REQ-12: Resource Links

Each service report includes complete lists of the underlying resources. Jira keeps delivered and created stories separate; Bitbucket returns merged PRs.

**JSON structure:**
```json
"links": {
  "delivered_stories": [
    { "key": "CI-123", "url": "https://jira.company.com/browse/CI-123", "points": 5 },
    ...
  ],
  "created_stories": [
    { "key": "CI-456", "url": "https://jira.company.com/browse/CI-456", "points": 3 },
    ...
  ]
}
```

```json
"links": {
  "merged_prs": [
    { "id": 42, "url": "https://bb.company.com/projects/CI/repos/repo1/pull-requests/42" },
    ...
  ]
}
```

**Acceptance criteria:**
- AC1: Lists contain all matching resources; output is not truncated.
- AC2: Links are full URLs, not relative paths.
- AC3: If zero resources → empty array `[]`.

### REQ-13: Multiple Employee Output

When multiple `--email` values are provided, the selected command outputs a JSON array. The `jira` and `bitbucket` commands have separate schemas and never include metrics from the other service.

**JSON structure:**
```json
[
  { "email": "alice@...", "period": {...}, "metrics": {...}, "links": {...} },
  { "email": "bob@...", "period": {...}, "metrics": {...}, "links": {...} }
]
```

**Acceptance criteria:**
- AC1: Same structure for single and multiple employees (always an array).
- AC2: If any employee lookup fails in the selected service, the tool exits with one error listing every failed email: `Error: Employees not found in Jira: <email>, ...` or `Error: Employees not found in Bitbucket: <email>, ...`.

### REQ-14: Error Handling

- **Employee not found in Jira:** Exit with code 1 and one list-form message for all failed lookups: `Error: Employees not found in Jira: <email>, ...`.
- **Employee not found in Bitbucket:** Exit with code 1 and one list-form message for all failed lookups: `Error: Employees not found in Bitbucket: <email>, ...`.
- **Story Points field missing:** Exit with code 1, message `Error: Jira field 'Story Points' not found`.
- **Story Points field ambiguous:** Exit with code 1, message `Error: Multiple Jira fields named 'Story Points' found`.
- **Project not found:** Exit with code 1 and identify the selected service and configured project key.
- **API connection error:** Exit with code 1, message `Error: <error details>`.
- **Invalid dates:** Exit with code 1, message `Error: Invalid date format. Use YYYY-MM-DD.`.
- **Reversed date range:** Exit with code 1, message `Error: --from must be on or before --to`.
- **Missing .env:** Exit with code 1, message `Error: .env file not found`.

## Output Schemas

### Jira

```json
[
{
  "email": "alice@company.com",
  "period": {
    "from": "2026-08-01",
    "to": "2026-08-31"
  },
  "metrics": {
    "total_story_points": 42,
    "stories_delivered": 10,
    "stories_created": 5,
    "stories_carried_over": 2,
    "carry_over_percentage": 15.4,
    "average_cycle_time_days": 5.3,
    "average_sp_per_sprint": 14.0
  },
  "links": {
    "delivered_stories": [
      { "key": "CI-123", "url": "https://jira.company.com/browse/CI-123", "points": 5 },
      ...
    ],
    "created_stories": [
      { "key": "CI-456", "url": "https://jira.company.com/browse/CI-456", "points": 3 },
      ...
    ]
  }
}
]
```

### Bitbucket

```json
[
{
  "email": "alice@company.com",
  "period": {
    "from": "2026-08-01",
    "to": "2026-08-31"
  },
  "metrics": {
    "total_merged_prs": 8,
    "prs_by_repo": {
      "ci-audit": 5,
      "ci-core": 3
    },
    "review_comments": 12,
    "average_pr_turnaround_hours": 18.5
  },
  "links": {
    "merged_prs": [
      { "id": 42, "url": "https://bb.company.com/projects/CI/repos/repo1/pull-requests/42" },
      ...
    ]
  }
}
]
```

All metrics fields for the selected service are always present, even if zero or `null`.

## Project Structure

```
TeamMetrics/
├── pyproject.toml          # project config, dependencies
├── README.md
├── .env.example            # template for .env
├── .env                    # (gitignored) actual credentials
├── src/
│   └── teammetrics/
│       ├── __init__.py
│       ├── __main__.py     # entry point: python -m teammetrics
│       ├── cli.py          # argparse and jira/bitbucket subcommands
│       ├── config.py       # .env loading, selected-service validation
│       ├── period.py       # local-time half-open period handling
│       ├── jira_client.py  # Jira Data Center API client
│       ├── bitbucket_client.py  # Bitbucket Data Center API client
│       ├── jira_metrics.py # Jira metric calculation logic
│       ├── bitbucket_metrics.py # Bitbucket metric calculation logic
│       └── output.py       # JSON serialization, formatting
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_period.py
│   ├── test_jira_client.py
│   ├── test_jira_metrics.py
│   ├── test_bitbucket_client.py
│   ├── test_bitbucket_metrics.py
│   ├── test_reports.py
│   └── test_cli.py
├── docs/
│   └── adr/
│       ├── 0001-use-atlassian-python-api.md
│       ├── 0002-token-based-auth.md
│       ├── 0003-python-313-uv.md
│       └── 0004-json-output-format.md
└── uv.lock
```

## Dependencies

**Runtime:**
- `atlassian-python-api` — Jira + Bitbucket API abstraction
- `python-dotenv` — `.env` file parsing

**Dev:**
- `pytest` — testing framework
- `ruff` — linting and formatting

**Python version:** 3.13+

## Example Usage

```bash
# Jira metrics for one employee
python -m teammetrics jira --from 2026-08-01 --to 2026-08-31 --email alice@company.com

# Bitbucket metrics for multiple employees
python -m teammetrics bitbucket --from 2026-08-01 --to 2026-08-31 \
  --email alice@company.com --email bob@company.com

# Verbose Jira output
python -m teammetrics jira --from 2026-08-01 --to 2026-08-31 --email alice@company.com -v
```
