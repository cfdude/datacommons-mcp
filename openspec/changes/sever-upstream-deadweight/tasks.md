## 1. Delete dead code & orphaned files (`repo-cleanliness`)

- [ ] 1.1 Delete the ADK/Gemini trees: `git rm -r evals/ examples/`.
- [ ] 1.2 Delete the dead module `datacommons_mcp/data_models/charts.py` (verified zero importers); confirm it is not re-exported in `data_models/__init__.py`.
- [ ] 1.3 Delete `functional_test.py` (root-level manual script) and `SPRINT_2_INTEGRATION.md`.
- [ ] 1.4 Verify nothing references the removed names: `rg "google\.adk|google-adk"` → empty; `rg -t py "charts"` → no live import of the deleted module.

## 2. Stop tracking runtime data (`repo-cleanliness`)

- [ ] 2.1 `git rm` the tracked runtime output: `git rm datacommons-data/observations/*.csv` (remove the empty dir from tracking).
- [ ] 2.2 Add `datacommons-data/` to `.gitignore`.

## 3. Dependency cleanup (`lean-dependencies`)

- [ ] 3.1 In `pyproject.toml` runtime deps, remove `fastapi`, `tiktoken`, and `httpx` (all verified zero direct imports; `httpx` stays transitively via fastmcp).
- [ ] 3.2 In `pyproject.toml` `[project.optional-dependencies].dev`, remove `respx` (unused).
- [ ] 3.3 Add `click` as a bounded direct dependency (e.g. `click>=8.0,<9`) — used by `cli.py` + `tests/test_cli.py`.
- [ ] 3.4 Run `uv lock` and `uv sync --extra dev`; confirm `httpx` still resolves transitively in `uv.lock`.

## 4. Trim documentation (`repo-cleanliness`)

- [ ] 4.1 Delete `docs/internal/evals.md` (documents only the removed eval suite).
- [ ] 4.2 Trim ADK/Gemini/eval references from `README.md`, `docs/quickstart.md`, `docs/user_guide.md`, `docs/extension-compatibility.md` (remove those sections/instructions; keep the MCP-server content).
- [ ] 4.3 Grep docs for dangling links/paths to deleted files (`evals/`, `examples/`, `internal/evals.md`) and fix/remove any.
- [ ] 4.4 Remove now-dead ignore patterns from `.mcpbignore` (`**/evals/`, `SPRINT_*.md`) — they reference deleted paths and contradict the repo-cleanliness goal of no dangling references to removed features.

## 5. Verification & integration

- [ ] 5.1 `rg "google\.adk|google-adk"` across the repo → empty; `git ls-files datacommons-data/` → empty.
- [ ] 5.2 Confirm every declared dep in `pyproject.toml` is imported (no unused) and every directly-imported package is declared (`click` present).
- [ ] 5.3 Final gate: `uv run ruff format --check && uv run ruff check && uv run pytest -m "not e2e"` all green; `uv lock --check` consistent; server boots via `python datacommons_mcp/run_server.py` (EOF) with no import errors.
- [ ] 5.4 Commit per logical group (conventional commits), then proceed to Gate 2 (Superpowers code review) before finalizing.
