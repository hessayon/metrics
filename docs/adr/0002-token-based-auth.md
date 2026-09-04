# ADR-002: Token-based authentication for self-hosted Jira and Bitbucket

## Status
Accepted

## Context
Both Jira and Bitbucket are self-hosted (Data Center). Authentication must use tokens,
not basic auth (username/password) or OAuth. The `atlassian-python-api` library supports
token auth but Data Center token format differs between Jira and Bitbucket:
- Jira Data Center: token passed via `Authorization: Bearer <token>` header
- Bitbucket Data Center: personal access token (PAT) passed via `Authorization: Bearer <token>`

## Decision
Use Bearer-token authentication for both services. Tokens are read from
`Path.cwd() / ".env"`. The library instances are configured with the raw token value
and send `Authorization: Bearer <token>`.

## Consequences
- No credentials stored in code or version control.
- `.env.example` provides a template for new users.
- Data Center deployments must support Bearer tokens; Basic-auth fallback is outside
  this tool's contract.
