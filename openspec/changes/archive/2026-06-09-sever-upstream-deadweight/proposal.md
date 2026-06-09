## Why

`datacommons-mcp` is a fork of the upstream `datacommonsorg/agent-toolkit` and still carries dead weight from it. Dead weight is judged here by **value and fit to this MCP server**, not merely by whether something is imported:

- **The Google ADK / Gemini code (`evals/`, `examples/`) fails the fit test outright.** It is not part of the server — it is a *client* of it: a sample `LlmAgent` and a Gemini-powered eval harness that consume the server's tools via `MCPToolset`. A consumer of the server has no business shipping *inside* the server's package (it belongs in docs or a separate repo). It is also stale and unmaintainable here: `google-adk` is **undeclared and unpinned**, written against a ~2025 API, while the framework has since churned through **71 releases to 2.2.0** (0.x→2.x) — so it cannot even import, let alone run.
- **The rest is conventional dead weight:** a dead module with zero importers, a loose root-level manual test, a sprint doc, runtime CSV output committed to git, and declared-but-unused dependencies (`fastapi`, `tiktoken`, `httpx`, `respx`). `click` is used by the CLI but only present transitively.

This is change #2 of the overhaul (`docs/audits/2026-06-08-forensic-review.md`), sequenced right after security because it is pure deletion with verified zero/contained blast radius and it unblocks the later refactors by shrinking the surface. (The deeper value/fit evaluation of *live* code — does each module earn its place? — is applied in change #4 `modularize-core`.)

## What Changes

- **Sever the ADK/Gemini coupling. BREAKING (removes non-functional features):** delete `evals/` (whole tree) and `examples/sample_agents/` — both import `google.adk`, are excluded from the test path, and cannot run.
- **Delete dead/orphaned files:** `datacommons_mcp/data_models/charts.py` (zero importers), `functional_test.py` (root-level manual script), `SPRINT_2_INTEGRATION.md`.
- **Stop tracking runtime data:** `git rm` the committed `datacommons-data/observations/*.csv` and add `datacommons-data/` to `.gitignore`.
- **Drop unused dependencies** from `pyproject.toml`: `fastapi`, `tiktoken`, `httpx` (redundant — transitive via fastmcp), and dev dep `respx` (all verified zero imports across `datacommons_mcp/` and `tests/`).
- **Declare `click`** as an explicit, bounded direct dependency (used in `cli.py` + `tests/test_cli.py`, currently only transitive via uvicorn).
- **Trim ADK/Gemini references from docs** (`README.md`, `docs/quickstart.md`, `docs/user_guide.md`, `docs/extension-compatibility.md`, `docs/internal/evals.md`) so no dangling references remain.
- **Re-lock** `uv.lock` and validate the full test suite + server boot still pass.

Non-goals (deferred to later changes): consolidating `settings.py` (#3 `unify-configuration`); splitting the god modules (#4 `modularize-core`); `src/` layout + `servers/`→`tools/` rename (#5). `evals.yaml` and dependency bounds were already handled in change #1.

## Capabilities

### New Capabilities
- `lean-dependencies`: dependency declarations match actual usage — every declared dependency is imported by the code, every top-level import the code relies on is declared (no implicit reliance on transitives), and unused dependencies are removed.
- `repo-cleanliness`: the repository contains no dead/orphaned code, no upstream-fork ADK/Gemini coupling, no runtime output committed to version control, and no documentation references to removed features.

### Modified Capabilities
<!-- None — these are new quality concerns not covered by the existing dependency-security / supply-chain-scanning / ci-release-safety specs. -->

## Impact

- **Dependencies:** `pyproject.toml` (drop `fastapi`/`tiktoken`/`httpx`/`respx`, add `click`), `uv.lock` (regenerated).
- **Deleted code/files:** `evals/`, `examples/`, `data_models/charts.py`, `functional_test.py`, `SPRINT_2_INTEGRATION.md`, tracked `datacommons-data/observations/*.csv`.
- **Docs:** trim ADK/Gemini/eval references across 5 doc files.
- **`.gitignore`:** add `datacommons-data/`.
- **Risk:** low — every deletion target was verified by the forensic review to have zero or contained blast radius; the test suite + server boot are the regression gate. `charts.py` confirmed zero importers; the dropped deps confirmed zero imports.
