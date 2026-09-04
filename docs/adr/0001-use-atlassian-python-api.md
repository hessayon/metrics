# ADR-001: Use `atlassian-python-api` for Jira and Bitbucket

## Status
Accepted

## Context
We need to interact with both Jira Data Center and Bitbucket Data Center APIs from Python.
Two options were considered:
1. Use `atlassian-python-api` — a single library covering both Jira and Bitbucket Server.
2. Use `jira` (Cloud-focused) + `atlassian-python-api` (Bitbucket) — split libraries.
3. Use raw `requests` for both.

## Decision
Use `atlassian-python-api` for both Jira and Bitbucket. It supports both Data Center and
Cloud variants, provides a consistent API surface, and handles URL construction, header
management, and pagination internally.

## Consequences
- We get a unified abstraction over two Atlassian products.
- If a specific Data Center endpoint is not exposed by the library, we can fall back to
  raw `requests` with the same auth headers.
- The library adds a transitive dependency on `requests` and `urllib3`, which we already
  need.
