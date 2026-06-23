## Why

The test suite and CI work, but the overhaul left real gaps — and the `src/`-layout migration silently broke two CI behaviors:

- **CI tests can be silently skipped (falsely green).** `ci.yaml`'s `paths-filter` still gates on `datacommons_mcp/**`, but the code moved to `src/datacommons_mcp/**` (#33). A PR changing only `src/` code no longer matches → the pytest step is skipped while the job still passes.
- **CI excludes the wrong tests.** It runs `pytest -k "not eval"` — a *name* filter left over from the deleted eval suite — instead of `-m "not e2e"`. The live e2e tests (marked `@pytest.mark.e2e`, names don't contain "eval") are not reliably excluded.
- **No 3.13 in the matrix** despite `requires-python <3.14` and a `3.13` classifier.
- **Markers defined but unused.** `unit`/`integration` are declared in `pyproject` but never applied — there are no real tiers (only `e2e`, and one `slow`, are marked).
- **No coverage gate** (pytest-cov is a dev dep but unused; current baseline is **84%**).
- **No type checking** (mypy: 53 errors today under a lenient config — a fixable baseline).
- **`*_test.py` collection footgun** — `python_files = ["test_*.py", "*_test.py"]` will collect any `*_test.py` helper as tests (all 18 current test files use the `test_` prefix, so the suffix glob only adds risk).
- **No extension-bundle runtime-build smoke test** — the exact gap that let the macOS/Windows extension regression ship: `bash build-extension.sh` only *packages*; nothing runs the first-launch `uv run --frozen` editable build.

This is roadmap item #6, routed via OpenSpec (multiple specifiable, testable CI/test requirements).

## What Changes

- **Fix CI correctness:** `paths-filter` → `src/datacommons_mcp/**`; test selection → `-m "not e2e"`; add `3.13` to the matrix.
- **Real test tiers:** a `conftest.py` `pytest_collection_modifyitems` hook auto-marks any test without an `e2e`/`integration` marker as `unit`, and the genuinely cross-component tests get `@pytest.mark.integration`. CI then runs `unit` + `integration` (excluding `e2e`) and the markers become meaningful (`pytest -m unit`, `-m integration`, `-m e2e`).
- **Coverage gate:** run with `--cov=datacommons_mcp --cov-fail-under=80` (a stable floor below the 84% baseline; ratchets against regressions without flaking).
- **Static typing:** add `mypy` (dev extra) with a pragmatic, non-strict config; resolve the 53 baseline errors (fix the cheap ones, targeted `# type: ignore`/per-module overrides where a fix is disproportionate) so `mypy` passes clean, and add it as a CI step.
- **Close the collection footgun:** `python_files = ["test_*.py"]`.
- **Extension-build smoke test (the headline guard):** a CI job that assembles the bundle and runs `uv run --frozen --project <bundle> python -c "import datacommons_mcp"` — the first-launch editable build — so the regression class can never ship silently again.

Non-goals: NOT consolidating the duplicate lint/test gate in `build-and-publish.yaml` (works; out of scope — noted for later); NOT raising coverage above the current baseline (this adds the *gate*, not new tests); NOT mypy `--strict`.

## Capabilities

### New Capabilities
- `testing-and-ci-hardening`: the project has real test tiers (unit/integration/e2e), a coverage floor, static type checking, a 3.13 CI matrix, correct CI test selection/path-filtering, and an extension-bundle runtime-build smoke test guarding the first-launch editable build.

## Impact

- **Code/config:** `.github/workflows/ci.yaml` (path-filter, `-m "not e2e"`, 3.13, coverage, mypy, smoke-test job), `pyproject.toml` (python_files, mypy config + dev dep, coverage config), `tests/conftest.py` (auto-`unit` marker), targeted `@pytest.mark.integration` on cross-component tests, and small type fixes across `src/` for mypy.
- **Risk:** LOW–MEDIUM. The CI fixes are correctness wins (more is run, not less). mypy fixes touch source but are type-only (behavior-preserving); the suite + both review gates verify. The smoke test is additive.
