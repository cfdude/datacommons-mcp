## ADDED Requirements

### Requirement: No pre-release dependencies in production
The project SHALL NOT depend on a pre-release (alpha/beta/rc) version of any runtime dependency. Each runtime dependency SHALL resolve to a stable release.

#### Scenario: FastMCP resolves to a stable release
- **WHEN** dependencies are resolved from `pyproject.toml` and `uv.lock`
- **THEN** `fastmcp` resolves to a stable `3.x` release (constraint `>=3.4,<4`), not `3.0.0b1` or any pre-release

#### Scenario: No beta/rc anywhere in the lockfile for runtime deps
- **WHEN** `uv.lock` is inspected for runtime (non-dev) packages
- **THEN** no runtime package version contains a pre-release suffix (`a`, `b`, `rc`)

### Requirement: All direct dependencies are version-bounded
Every direct dependency declared in `pyproject.toml` SHALL have both a lower bound and an upper (major) bound (`>=X,<NEXT_MAJOR`).

#### Scenario: Previously unbounded deps are bounded
- **WHEN** `pyproject.toml` is inspected
- **THEN** `requests`, `datacommons-client`, and `pydantic-settings` each declare a lower and upper bound (no bare or open-ended specifiers remain)

### Requirement: Known CVEs are resolved or explicitly documented
All dependency CVEs reported by Trivy SHALL be remediated by upgrading to a patched version, OR — where no fix exists — documented with an accepted-risk rationale.

#### Scenario: Patched versions adopted for fixable CVEs
- **WHEN** Trivy scans the dependency set after this change
- **THEN** `authlib`, `cryptography`, `pyjwt`, `urllib3`, `requests`, `python-multipart`, `python-dotenv`, `pytest`, and `pygments` resolve to versions at or above their published fixed versions

#### Scenario: Unfixable CVE is documented
- **WHEN** a dependency CVE has no published fix (e.g. `diskcache` CVE-2025-69872)
- **THEN** the project records an accepted-risk note (exploitability assessment + monitoring intent) rather than leaving it untracked

### Requirement: Lockfile is current and reproducible
`uv.lock` SHALL be regenerated to match the updated `pyproject.toml` constraints and committed, so installs are deterministic.

#### Scenario: Lockfile matches the manifest
- **WHEN** `uv lock --check` (or equivalent) runs against the committed `uv.lock`
- **THEN** it reports the lock is consistent with `pyproject.toml` (no drift)

### Requirement: The external-data dependency is pinned against silent drift
Because observation lineage is mapped from `datacommons-client` model fields via `default=None` aliases (a silent-failure surface per the live-API analysis), `datacommons-client` SHALL be version-bounded and its observation contract guarded by a test.

#### Scenario: datacommons-client is bounded
- **WHEN** `pyproject.toml` is inspected
- **THEN** `datacommons-client` declares an upper bound (not open-ended)

#### Scenario: Observation lineage contract is guarded by a fixture-backed test
- **WHEN** a contract test parses the saved `docs/audits/api-samples/v2-observation.json` fixture through the `datacommons-client` observation models into `FacetMetadata`
- **THEN** parsing succeeds without error, `import_name` and `provenance_url` map non-null for every facet, AND a fully-populated facet (`4181918134`, which carries all four fields) maps `import_name`, `measurement_method`, `observation_period`, and `provenance_url` non-null
- **AND** the optional fields (`measurement_method`, `observation_period`) are asserted only where the fixture actually provides them (they are legitimately absent on some facets), so the test guards mapping correctness without asserting `None` as a value

#### Scenario: Existing test suite passes against upgraded dependencies
- **WHEN** the test suite runs after the dependency upgrades
- **THEN** all non-e2e tests pass (no regressions introduced by the FastMCP beta→GA jump or other bumps)
