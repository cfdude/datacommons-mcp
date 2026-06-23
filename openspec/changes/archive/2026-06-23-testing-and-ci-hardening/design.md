## Context

`ci.yaml` runs ruff + `pytest -k "not eval"` on a 3.11/3.12 matrix, gated by a `paths-filter` that still references the pre-`src/` path. `pyproject` defines `unit`/`integration`/`slow`/`e2e` markers but only `e2e` is used (on `tests/test_e2e.py`). pytest-cov is a dev dep but unused; coverage baseline is 84%. No mypy. `build-extension.sh` packages the bundle but nothing exercises the first-launch `uv run --frozen` editable build (the regression that broke macOS+Windows).

## Decisions

**1. Auto-`unit` marker via `conftest.py` rather than hand-marking 17 files.** A `pytest_collection_modifyitems` hook adds `unit` to any item not already marked `integration`/`e2e`. This makes the tiers real and runnable (`-m unit/integration/e2e`) without tedious per-test churn, and stays correct as tests are added. Only the genuinely cross-component tests get an explicit `@pytest.mark.integration` (e.g. `test_integration.py`, `test_observation_contract.py`). *Alternative (mark every file):* rejected — churn + drift risk.

**2. Coverage floor = 80, not 84.** Gate on a stable floor below the current 84% so normal change doesn't flake CI, while still catching real regressions. *Alternative (fail-under=84):* rejected — brittle.

**3. mypy: pragmatic, not strict.** Config: `ignore_missing_imports`, no `--strict`. Resolve the 53 baseline errors by fixing the cheap/real ones and using targeted `# type: ignore[code]` or `[[tool.mypy.overrides]]` per-module where a proper fix is disproportionate (e.g. third-party-shaped dynamic responses). Goal: `mypy` exits 0 as a forward gate, not a strict-typing rewrite. *Alternative (strict):* rejected — disproportionate for a working, well-tested codebase.

**4. Extension smoke test reuses the real build script via a `--no-pack` mode.** Add `--no-pack` to `build-extension.sh` (assemble `build/` exactly as today but skip the `mcpb pack` step, which needs the `mcpb` CLI). The CI smoke job runs `bash build-extension.sh --no-pack` then `uv run --frozen --project build python -c "import datacommons_mcp"`. This exercises the **actual** assembly (flattening + the `where=["."]` pyproject transform) and the first-launch editable build — no duplicated logic, and it would have caught the regression. *Alternative (a pytest test that shells out):* rejected — the bundle build is a CI/integration concern, cleaner as a dedicated job; keeping it out of the unit suite keeps `pytest` fast.

**5. CI test step gains coverage; keep it one ruff+pytest gate.** The non-e2e run becomes `pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80`. mypy is a sibling step. (Consolidating the duplicate gate in `build-and-publish.yaml` is a non-goal.)

## Risks / Trade-offs

- **mypy fixes touch source** → type-only, behavior-preserving; the full suite + Gate 2 verify nothing changed at runtime.
- **The auto-`unit` hook could mis-tier** → it only *adds* `unit` when no `integration`/`e2e` marker is present; explicit markers always win.
- **The smoke job needs `uv` + network** (first-launch downloads deps) → acceptable for a dedicated CI job; pin via `--frozen`.

## Migration Plan

1. `pyproject.toml`: `python_files = ["test_*.py"]`; add `[tool.coverage.*]` + `[tool.mypy]` config; add `mypy` to the `dev` extra.
2. `tests/conftest.py`: add the auto-`unit` collection hook; mark the cross-component tests `integration`.
3. Fix the 53 mypy errors → clean pass (`uv run mypy src/datacommons_mcp`).
4. `build-extension.sh`: add `--no-pack` (assemble, skip `mcpb pack`).
5. `.github/workflows/ci.yaml`: path-filter → `src/datacommons_mcp/**`; test step → `-m "not e2e" --cov ... --cov-fail-under=80`; add `3.13`; add a `mypy` step; add an `extension-build-smoke` job.
6. Gate: full suite green per tier, mypy clean, coverage ≥ 80, `bash build-extension.sh --no-pack` + import succeeds locally.

**Rollback:** revert; config/CI-only + type-only source edits.
