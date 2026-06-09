## Context

This change removes upstream-fork dead weight identified in `docs/audits/2026-06-08-forensic-review.md` (Dead Code section), which verified blast radius for each target with `rg`/`git`. It is deliberately subtractive: deletions, dependency removals, and doc trims — no refactors. The test suite (228 non-e2e tests: the 223 pre-existing plus the 5 contract tests added in change #1) plus a server-boot smoke are the regression gate.

## Goals / Non-Goals

**Goals:**
- Remove all ADK/Gemini coupling (`evals/`, `examples/`) and dead files (`charts.py`, `functional_test.py`, `SPRINT_2_INTEGRATION.md`).
- Make `pyproject.toml` dependencies match real usage (drop 4 unused, declare `click`).
- Stop tracking runtime output; trim docs of references to removed features.

**Non-Goals:**
- No `settings.py` consolidation (#3), no module splits (#4), no `src/` layout/rename (#5).
- No new functionality; no behavior change to the two MCP tools.
- Deleting `functional_test.py` removes today's only root-level `*_test.py`, but does NOT close the underlying `python_files = ["*_test.py"]` glob footgun (`pyproject.toml`) — that hardening belongs to change #6 (`testing-and-ci-hardening`).

## Decisions

**1. Delete `functional_test.py` rather than relocate it.** It is an un-asserted `__main__` manual script, not a test. *Alternative:* move to `scripts/smoke_stdio.py`. *Rejected for now:* keep this change purely subtractive; a proper `@pytest.mark.e2e` stdio smoke test can be (re)introduced deliberately in change #6 (`testing-and-ci-hardening`) where the test strategy is designed.

**2. Delete `docs/internal/evals.md` entirely; trim (not delete) the other four docs.** `docs/internal/evals.md` documents only the removed eval suite, so it becomes orphaned — delete it. `README.md`, `docs/quickstart.md`, `docs/user_guide.md`, and `docs/extension-compatibility.md` also document the real MCP server, so only their ADK/Gemini/eval sections are trimmed. *Guard:* after trimming, grep the docs for links/paths pointing at deleted files (`evals/`, `examples/`, `internal/evals.md`) to avoid dangling references.

**3. Drop `httpx` as a direct declaration but expect it to remain in `uv.lock` transitively** (fastmcp depends on it). The code never imports it directly, so the direct pin only adds maintenance burden. *Verification:* confirm `httpx` still resolves in the regenerated lock (via fastmcp) so nothing breaks.

**4. `click` gets the same bounded policy as change #1** — `click>=8.0,<9` (or the current major's range), consistent with the "every direct dep bounded" requirement established in `dependency-security`.

## Risks / Trade-offs

- **A hidden reference to a deleted file/symbol** → Mitigation: `rg` for each removed name (`charts`, `evals`, `examples`, `google.adk`) across the repo before and after; run the full suite + import the package + boot the server.
- **Doc trim leaves a broken internal link** → Mitigation: grep docs for paths to deleted files; fix or remove those links.
- **Dropping a dep that is actually needed at runtime but not at import time** → Low: the four targets were verified zero-import; the server-boot smoke catches any runtime-only need. If boot fails, restore the specific dep.

## Migration Plan

1. Delete files (`evals/`, `examples/`, `charts.py`, `functional_test.py`, `SPRINT_2_INTEGRATION.md`); `git rm` the tracked CSV; add `datacommons-data/` to `.gitignore`.
2. Edit `pyproject.toml` (drop 4 deps, add bounded `click`); `uv lock`; `uv sync`.
3. Trim/delete docs; grep for dangling references.
4. Validate: `rg google.adk` empty, package imports, `ruff` clean, non-e2e suite green, server boots.

**Rollback:** revert the change's commits; `git` restores deleted files and the lockfile. No data migration involved.
