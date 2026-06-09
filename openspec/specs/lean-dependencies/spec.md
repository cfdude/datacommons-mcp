# lean-dependencies Specification

## Purpose
TBD - created by archiving change sever-upstream-deadweight. Update Purpose after archive.
## Requirements
### Requirement: Declared dependencies match actual usage
Every dependency declared in `pyproject.toml` (runtime and dev) SHALL either be imported somewhere in the package or tests, OR be a documented direct pin of a transitive dependency held for security reasons. Dependencies that are neither used nor a documented security pin SHALL be removed.

#### Scenario: Unused runtime dependencies are removed
- **WHEN** `pyproject.toml` runtime dependencies are inspected
- **THEN** `fastapi`, `tiktoken`, and `httpx` are no longer declared (each verified to have zero imports across `datacommons_mcp/` and `tests/`; `httpx` remains available transitively via `fastmcp`)

#### Scenario: Security-driven transitive pins are retained
- **WHEN** a declared dependency is not directly imported but exists to force a patched version of a transitive (e.g. `cryptography`, pinned in the `dependency-security` change for `fastmcp`→`authlib`→`cryptography`)
- **THEN** it is retained, not removed, and its rationale remains documented

#### Scenario: Unused dev dependencies are removed
- **WHEN** `pyproject.toml` `[project.optional-dependencies].dev` is inspected
- **THEN** `respx` is no longer declared (tests mock `requests` via `unittest.mock`, not `respx`)

### Requirement: Directly-used imports are explicitly declared
Any third-party package imported directly by the code SHALL be declared as a direct dependency, rather than relied upon transitively.

#### Scenario: click is an explicit, bounded dependency
- **WHEN** `pyproject.toml` is inspected
- **THEN** `click` is declared as a direct dependency with lower and upper bounds (it is imported by `datacommons_mcp/cli.py` and `tests/test_cli.py`, and was previously only present transitively via uvicorn)

### Requirement: The lockfile and build remain valid after dependency changes
After dependency changes, `uv.lock` SHALL be regenerated and the package SHALL still build, import, and pass its tests.

#### Scenario: Lockfile consistent and suite green
- **WHEN** `uv lock --check` runs and the non-e2e test suite is executed after the dependency edits
- **THEN** the lock is consistent with `pyproject.toml` and all non-e2e tests pass

#### Scenario: Server still boots
- **WHEN** the stdio server entry point is launched after the dependency removals
- **THEN** the FastMCP server starts and registers its tools without import errors

