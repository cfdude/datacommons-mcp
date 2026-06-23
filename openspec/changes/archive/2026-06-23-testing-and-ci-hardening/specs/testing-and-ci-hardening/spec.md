## ADDED Requirements

### Requirement: CI runs the correct tests on the correct paths
CI SHALL detect changes under the real source path and exclude e2e tests by marker, across the supported Python matrix.

#### Scenario: Tests always run (no conditional skip)
- **WHEN** any push or PR to `main` triggers CI
- **THEN** the test step runs unconditionally — the `paths-filter` step and its `if: run_tests == 'true'` guard are removed — so no change (incl. `src/`-only, `pyproject.toml`, or build-script changes) can leave the suite skipped while the job reports green

#### Scenario: e2e tests are excluded by marker
- **WHEN** the CI test step runs
- **THEN** it uses `pytest -m "not e2e"` (not the legacy `-k "not eval"` name filter), so `@pytest.mark.e2e` tests are excluded

#### Scenario: The matrix covers all supported Python versions
- **WHEN** the CI matrix is evaluated
- **THEN** it includes `3.11`, `3.12`, and `3.13` (matching `requires-python` and the classifiers)

### Requirement: Tests are organized into runnable tiers
Every test SHALL belong to exactly one tier — `unit`, `integration`, or `e2e` — selectable by marker.

#### Scenario: Unmarked tests default to the unit tier
- **WHEN** the suite is collected
- **THEN** a `conftest.py` hook assigns `unit` to any test not already marked `integration` or `e2e`, so `pytest -m unit`, `pytest -m integration`, and `pytest -m e2e` each select a disjoint, non-empty set

#### Scenario: Cross-component tests are marked integration
- **WHEN** a test exercises multiple real components together (not isolated mocks)
- **THEN** it carries `@pytest.mark.integration`

### Requirement: A coverage floor gates CI
CI SHALL fail if line coverage drops below a defined floor.

#### Scenario: Coverage below the floor fails the build
- **WHEN** the non-e2e suite runs in CI with coverage
- **THEN** it runs `--cov=datacommons_mcp --cov-fail-under=80` and fails if coverage is under 80% (baseline is ~84%)

### Requirement: Static type checking gates CI
The project SHALL type-check clean under mypy, enforced in CI.

#### Scenario: mypy passes and is enforced
- **WHEN** `mypy` runs over `src/datacommons_mcp` with the project config
- **THEN** it reports no errors, and CI runs `mypy` as a required step

### Requirement: Test collection is restricted to test_ files
Pytest SHALL only collect `test_*.py` files.

#### Scenario: The *_test.py suffix glob is removed
- **WHEN** `pyproject.toml`'s `[tool.pytest.ini_options].python_files` is inspected
- **THEN** it is `["test_*.py"]` (the `*_test.py` suffix is removed; no current test relies on it)

### Requirement: The extension bundle's first-launch build is smoke-tested
CI SHALL verify the extension bundle's runtime editable build (the step that broke the macOS/Windows install), not just that it packages.

#### Scenario: The bundle's editable build is exercised in CI
- **WHEN** the extension-build smoke job runs
- **THEN** it assembles the bundle (as `build-extension.sh` does, flattened, with the adapted `pyproject`) and runs `uv run --frozen --project <bundle> python -c "import datacommons_mcp"`, failing if the editable build or import fails
