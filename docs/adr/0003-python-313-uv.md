# ADR-003: Python 3.13 + uv for dependency management

## Status
Accepted

## Context
We need a Python runtime and dependency manager. Options considered:
1. `pip` + `venv` — traditional, but slower and without a project lockfile by default.
2. `poetry` — opinionated, adds lockfile and build system complexity.
3. `uv` — fast, modern, drop-in `pip`/`venv` replacement with lockfile.

## Decision
Use Python 3.13 with `uv` for dependency management. `uv` provides:
- Substantially faster dependency resolution and installation.
- `uv.lock` for deterministic builds.
- `uv run` for running CLI commands without activating the virtual environment.

## Consequences
- Developers must have `uv` installed (available via `pip install uv` or package manager).
- `pyproject.toml` replaces `requirements.txt` for dependency declarations.
- No need for `pip-tools` or `poetry.lock` — `uv.lock` serves both purposes.
