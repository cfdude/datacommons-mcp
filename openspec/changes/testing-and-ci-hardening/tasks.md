## 1. pyproject: collection, coverage, mypy config

- [ ] 1.1 `[tool.pytest.ini_options].python_files = ["test_*.py"]` (drop the `*_test.py` suffix glob). Verify no current test relies on the suffix (all 18 use the `test_` prefix).
- [ ] 1.2 Add coverage config: `[tool.coverage.run] source = ["datacommons_mcp"]` (+ omit tests), `[tool.coverage.report]` reasonable excludes.
- [ ] 1.3 Add `mypy` to `[project.optional-dependencies].dev`; add `[tool.mypy]` (target the package, `ignore_missing_imports = true`, NOT strict). `uv lock` to refresh.

## 2. Test tiers

- [ ] 2.1 `tests/conftest.py`: add `pytest_collection_modifyitems` that adds the `unit` marker to any item not already marked `integration` or `e2e`. (Create conftest.py if absent.)
- [ ] 2.2 Add module-level `pytestmark = pytest.mark.integration` to `tests/test_observation_contract.py` (verified: 0 mocks — a genuine contract/integration test). This UNCONDITIONALLY makes the `integration` tier non-empty (Gate-1 C1). Leave `tests/test_integration.py` as `unit` (it's mock-based — 15 mocks despite the name) and all other mock-based tests default to `unit`.
- [ ] 2.3 Verify the tiers are disjoint + non-empty: `pytest -m unit -q`, `pytest -m integration -q`, `pytest -m e2e --co -q` each select the expected sets; `-m "not e2e"` == unit + integration.

## 3. Static typing (mypy → clean)

- [ ] 3.1 Run `uv run --extra dev mypy src/datacommons_mcp`; resolve the ~53 errors. The bulk (~29 `[attr-defined]`) come from the DCClient mixin pattern (`_SearchMixin`/`_EntitiesMixin`/`_ObservationsMixin` reference `self.dc`/`self.variable_cache`/`self.topic_store`/… set in `DCClient.__init__`); collapse them with ONE `[[tool.mypy.overrides]] module = "datacommons_mcp.clients.*"` disabling `attr-defined` (document the trade-off: it also masks future typos in those modules — acceptable vs hand-declaring 29 attrs / a Protocol). Fix the remaining ~24 (trivial `var-annotated`, the `pagination_handler` assignment cluster, `config.py`/`observations.py` Optionals) with a line or targeted `# type: ignore[code]` each. Goal: exit 0.
- [ ] 3.2 Confirm `uv run --extra dev mypy src/datacommons_mcp` reports no errors and the full non-e2e suite still passes (type fixes are behavior-preserving).

## 4. Extension-build smoke (the regression guard)

- [ ] 4.1 `build-extension.sh`: add a `--no-pack` mode that assembles `build/` exactly as today (rsync `src/datacommons_mcp`, copy launchers, `sed` pyproject to `where=["."]`, copy uv.lock/README/LICENSE/manifest) but SKIPS the `mcpb pack`/`mv` steps. Default behavior unchanged.
- [ ] 4.2 Verify locally (GREEN): `bash build-extension.sh --no-pack && uv run --frozen --project build python -c "import datacommons_mcp; print(datacommons_mcp.__version__)"` succeeds. Then prove the guard FIRES (RED): temporarily change the bundle's `build/pyproject.toml` back to `where = ["src"]`, re-run the `uv run --frozen … import` and confirm it FAILS with the original `ModuleNotFoundError`, then restore/clean up `build/`. (This proves `uv run --project build` actually rebuilds the editable package — the whole point — not just imports via cwd.)

## 5. CI workflow (.github/workflows/ci.yaml)

- [ ] 5.1 REMOVE the `dorny/paths-filter` step and the `if: steps.filter.outputs.run_tests == 'true'` conditional on the test step — **always run the suite** (it's ~0.4s). This kills the falsely-green *skip class*, not just the stale path (Gate-1 I2): the filter also omitted `pyproject.toml`/`build-extension.sh`, so a dep bump or build-script change would have skipped tests and passed green.
- [ ] 5.2 Matrix: add `"3.13"` → `["3.11", "3.12", "3.13"]`.
- [ ] 5.3 Test step: `uv run --extra dev pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` (replaces `-k "not eval"`; adds the coverage floor).
- [ ] 5.4 Add a `mypy` step: `uv run --extra dev mypy src/datacommons_mcp`.
- [ ] 5.5 Add an `extension-build-smoke` job: checkout, install uv, `bash build-extension.sh --no-pack`, then `uv run --frozen --project build python -c "import datacommons_mcp"`. (Single OS is sufficient — the failure was layout/config, not OS-specific.)

## 6. Verification

- [ ] 6.1 Local gate: `uv run --extra dev ruff format --check && uv run --extra dev ruff check && uv run --extra dev mypy src/datacommons_mcp && uv run --extra dev pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` → all pass; `uv lock --check` consistent.
- [ ] 6.2 Tiers run cleanly: `pytest -m unit` and `pytest -m integration` both green.
- [ ] 6.3 Extension smoke passes locally (task 4.2).
- [ ] 6.4 Commit per logical group; push and confirm the CI matrix (incl. 3.13) + mypy + coverage + smoke job are all green on the PR before Gate 2.
