# ADR-004: JSON output format with links to resources

## Status
Accepted

## Context
The CLI needs to output metrics in a structured format. Options considered:
1. Human-readable table — convenient for quick inspection, but not machine-parseable.
2. JSON — structured, machine-parseable, embeds URLs to Jira stories and Bitbucket PRs.
3. YAML — readable but redundant; JSON covers both human and machine needs.

## Decision
Output JSON (via `json.dumps` with indentation). Each metric result includes:
- Numeric values (always present, even if zero).
- URLs to the corresponding Jira stories and Bitbucket PRs.
- A `period` field with `from` and `to` dates.

For multiple employees, the output is a JSON array. For a single employee, still a
single-element array — this keeps the consumer logic uniform.

## Consequences
- Consumers (scripts, CI, dashboards) can parse the output directly.
- Human readers may find JSON verbose; a `--format table` flag could be added later
  if needed.
