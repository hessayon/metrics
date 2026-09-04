# TeamMetrics CLI Implementation Plan

**Goal:** Build two independent CLI reports for one Jira project and one Bitbucket project, with complete linked resource lists.

**Commands:**

```bash
python -m teammetrics jira --from YYYY-MM-DD --to YYYY-MM-DD --email EMAIL [--email EMAIL ...]
python -m teammetrics bitbucket --from YYYY-MM-DD --to YYYY-MM-DD --email EMAIL [--email EMAIL ...]
```

**Constraints:** Python 3.13, `uv`, `atlassian-python-api`, `python-dotenv`, `pytest`, and `ruff`. Reuse one small pagination/date helper where both clients need it; do not introduce service interfaces or extension scaffolding.

**Authoritative behavior:** [OpenSpec](../../../openspec/specs/cli-team-metrics/spec.md). Each task below must leave its listed runnable check passing. Implementation tasks are assigned to subagents; after integration, a separate subagent reviews the complete diff.

## Task 1: Project skeleton, configuration, and CLI contract

**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `src/teammetrics/{__init__,__main__,cli,config}.py`, `tests/test_cli.py`, `tests/test_config.py`

- [ ] Create the package and console entry point.
- [ ] Add `jira` and `bitbucket` subcommands with shared `--from`, `--to`, repeatable `--email`, and `--verbose` arguments.
- [ ] Load `.env` from exactly `Path.cwd() / ".env"`, validate only the selected service's URL, token, and project key, and use Bearer authentication without a Basic fallback.
- [ ] Validate date syntax, ordering, missing emails, and documented exit messages, including `Error: --from must be on or before --to` for a reversed range.
- [ ] Put `JIRA_PROJECT` and `BITBUCKET_PROJECT` in `.env.example`; never require a board ID, username map, or timezone setting.

**Check:** `uv run pytest tests/test_cli.py tests/test_config.py -q`

## Task 2: Period handling

**Files:** `src/teammetrics/period.py`, `tests/test_period.py`

- [ ] Parse dates once and use the machine's local timezone.
- [ ] Represent the user-facing inclusive period as `[from 00:00, day-after-to 00:00)`.
- [ ] Convert timestamps returned by Jira and Bitbucket to local timezone before range checks.
- [ ] Use Jira date-only JQL only as a coarse candidate filter widened by two calendar days at each edge, then authoritatively filter Jira timestamps against the local half-open period; do not build a `23:59` upper bound.

**Check:** `uv run pytest tests/test_period.py -q`

## Task 3: Jira Data Center client

**Files:** `src/teammetrics/jira_client.py`, `tests/test_jira_client.py`

- [ ] Validate `JIRA_PROJECT` and employee emails through Jira.
- [ ] Discover the unique REST field ID whose exact name is `Story Points`; return the specified missing/ambiguous errors.
- [ ] Fetch paginated Story candidates for assignee and created Stories for reporter within the configured project, using date-only JQL bounds widened by two calendar days at each edge where dates constrain the candidate query.
- [ ] Fetch complete changelogs and select the first transition to `Ready For IFT` inside the period.
- [ ] Discover all project boards, keep Scrum boards, fetch all Sprints through Agile API with GreenHopper fallback, and deduplicate by numeric Sprint ID.
- [ ] Treat Agile API failure as optional metric unavailability, not as failure of the whole Jira report.

**Check:** `uv run pytest tests/test_jira_client.py -q`

## Task 4: Jira metrics and links

**Files:** `src/teammetrics/jira_metrics.py`, `tests/test_jira_metrics.py`

- [ ] Build `delivered_stories` from actual first `Ready For IFT` transitions in the period; current status and `updated` are not delivery evidence.
- [ ] Calculate delivered count and Story Points from the discovered field, with unset points contributing zero.
- [ ] Build the complete `created_stories` list and count from reporter, converting `created` to local time and applying the local half-open period after the widened JQL candidate query.
- [ ] For every delivered Story, pair its first in-period `Ready For IFT` transition with the nearest preceding transition into `work started` or `in progress`.
- [ ] Calculate cycle time only from valid pairs; return `null` when fewer than two valid pairs exist.
- [ ] Reconstruct Sprint membership chronologically as sets of numeric IDs from Sprint changelog `from`/`to` values. At each event, intersect membership with known Scrum Sprints satisfying `startDate <= event < endDate`; exactly one match resolves the Sprint, otherwise it is unknown. Count carry-over only when both resolved IDs differ.
- [ ] Keep deduplicated Scrum Sprints with parseable boundaries whose intervals strictly intersect the period (`startDate < day-after-to` and `endDate > from`). Assign delivery points to the resolved Sprint at delivery and average over all intersecting Sprints, including zero-delivery Sprints.
- [ ] On Agile API failure, output carry-over as `0`/`0.0` and average Story Points per Sprint as `null`.
- [ ] Return all delivered and created Story links without truncation.

**Check:** `uv run pytest tests/test_jira_metrics.py -q`

## Task 5: Bitbucket Data Center client

**Files:** `src/teammetrics/bitbucket_client.py`, `tests/test_bitbucket_client.py`

- [ ] Validate `BITBUCKET_PROJECT` and employee emails through Bitbucket.
- [ ] Enumerate and paginate every repository in the configured project, then paginate merged PRs and their activity streams; use the timestamp of the `MERGED` activity as merge time (never `closedDate` or `updated`) and extract comments from those activities.
- [ ] Match authors, reviewers, and comment authors by email only.
- [ ] Filter PRs by the actual merge timestamp in the local-time half-open period.
- [ ] Preserve the Bitbucket Data Center numeric PR `id`, repository slug, author/reviewer identities, created/merged timestamps, and full URL. Do not use a Cloud-style `uuid`.

**Check:** `uv run pytest tests/test_bitbucket_client.py -q`

## Task 6: Bitbucket metrics and links

**Files:** `src/teammetrics/bitbucket_metrics.py`, `tests/test_bitbucket_metrics.py`

- [ ] For PRs authored by the employee and merged in the period, calculate total count and counts by repository.
- [ ] Return the complete `merged_prs` list using numeric `id` and full URLs.
- [ ] Count only the employee's own in-period comments on PRs that were also merged in the period and list that employee as a reviewer.
- [ ] For each employee-authored merged PR, find the first comment written by any listed reviewer. Ignore comments from the author and non-reviewers.
- [ ] Average PR creation-to-first-valid-review-comment time; omit PRs without a valid reviewer comment and return `null` if none remain.

**Check:** `uv run pytest tests/test_bitbucket_metrics.py -q`

## Task 7: Service-specific report assembly

**Files:** `src/teammetrics/cli.py`, `src/teammetrics/output.py`, `tests/test_reports.py`

- [ ] Wire `jira` only to Jira and `bitbucket` only to Bitbucket so one service cannot break the other command.
- [ ] Always emit an array, including for one email, and always include every metric field for the selected service.
- [ ] Emit Jira links as separate `delivered_stories` and `created_stories` arrays; emit Bitbucket links as `merged_prs`.
- [ ] Keep resource arrays complete and JSON on stdout; send verbose progress and errors to stderr.
- [ ] Collect all failed employee lookups and report them once before exiting with code 1: `Error: Employees not found in Jira: <email>, ...` or the analogous Bitbucket message.

**Check:** `uv run pytest tests/test_reports.py tests/test_cli.py -q`

## Task 8: Integration and documentation

**Files:** `README.md`, all tests

- [ ] Document setup, both commands, selected-service configuration, machine-local timezone behavior, and example Jira/Bitbucket JSON.
- [ ] Add one fixture-driven integration test per command covering pagination, exact period boundaries, opposite extreme Jira/CLI timezone offsets, and complete resource lists.
- [ ] Run the full test and lint suite.

**Checks:**

```bash
uv run pytest -q
uv run ruff check .
uv run python -m teammetrics --help
uv run python -m teammetrics jira --help
uv run python -m teammetrics bitbucket --help
```

## Task 9: Independent review

- [ ] Assign a fresh subagent to review the complete diff against every OpenSpec requirement.
- [ ] Require evidence-backed findings ordered by severity, with file and line references.
- [ ] Have the implementing subagent fix confirmed findings and rerun the smallest affected check plus the full suite.
- [ ] Finish only when the reviewer has no blocking findings and all Task 8 checks pass.
