## Context

`datacommons-mcp` is a public repo with 26 open code-scanning alerts (4 stale CodeQL, 22 real Trivy CVEs), a beta core framework, disabled Dependabot/secret-scanning, and a `pull_request_target` eval workflow that is a secret-exfiltration footgun. Findings and evidence are in `docs/audits/2026-06-08-forensic-review.md`. This is change #1 of a 7-change overhaul; it is sequenced first because it is highest-severity and lowest-code-risk. Some controls are code/CI (commit-and-PR); others are repo-settings toggles that require GitHub **admin** scope via `gh api`.

## Goals / Non-Goals

**Goals:**
- Eliminate Critical/High dependency CVEs and the beta pin; bound all direct deps; keep `uv.lock` reproducible.
- Turn on the standard public-repo scanning posture (Dependabot, secret scanning, CodeQL) and clear stale alerts.
- Close the `pull_request_target` secret-exfiltration path and the orphan `evals-and-secrets` environment.
- Gate the PyPI release on passing CI.

**Non-Goals:**
- No SQLAlchemy/Alembic/FastAPI; no code refactor; no structured-output/error-model work (that is `modularize-core`).
- No deletion of `evals/`/`examples/` source (that is change #2) — only the insecure `evals.yaml` workflow is removed here.

## Decisions

**1. FastMCP: upgrade forward to 3.x stable, not back to 2.x.** Verified that FastMCP 3.0 is GA (latest 3.4.2); the server's own "pin < 3" runtime warning is stale advice from before GA. Constraint: `fastmcp>=3.4,<4`. *Alternative considered:* pin `fastmcp<3` (the 2.14.x line) — rejected as adopting a now-legacy line and discarding fixes. *Validation:* the existing 223-test suite is the regression gate for the beta→GA API delta; if a real blocker surfaces, fall back to a 2.x pin and flag it.

**2. CI-gate the publish workflow with an in-workflow job, not cross-workflow `needs:`.** `needs:` only works within a single workflow, and `ci.yaml` is separate. Decision: add a lint+test job inside `build-and-publish-datacommons-mcp.yaml` and make the build/publish job `needs:` it. *Alternative:* a `workflow_run` trigger gated on `ci.yaml` success — rejected as more fragile and harder to reason about than an explicit in-workflow gate.

**3. Delete `evals.yaml` rather than harden it.** The eval suite is non-functional (undeclared `google-adk`, excluded by `testpaths`, "exit 5 = pass") and is slated for deletion in change #2. Removing the workflow now is the simplest way to close the `pull_request_target` footgun. *Alternative:* refactor into a trusted no-checkout job + a separate secret-less `pull_request` job — rejected as effort spent hardening code that is about to be deleted.

**4. Repo-settings controls applied via `gh api` (admin), with a documented manual fallback.** Enabling Dependabot alerts, secret scanning + push protection, CodeQL default setup, and deleting the environment are settings changes, not code. They will be executed via `gh api` PATCH/PUT/DELETE. *Constraint:* these need admin scope; if the authenticated token lacks it, the tasks document the exact Settings-UI steps for the user.

**5. `diskcache` CVE-2025-69872 is accepted-with-monitoring.** No upstream fix exists. Decision: document the exploitability assessment and monitoring intent rather than pin away from `diskcache` (a transitive dep of fastmcp's stack). Revisit when a fix ships.

## Risks / Trade-offs

- **FastMCP GA API delta breaks code** → Mitigation: run the full non-e2e suite before committing; the lifespan/`Context`/tool-registration idioms were flagged by the MCP-standards review as "verify against GA docs." If broken, fix minimally here or fall back to a bounded 2.x pin and note it.
- **`gh` token lacks admin scope for settings toggles** → Mitigation: detect the 403/permission error and emit documented manual UI steps; do not silently skip.
- **Deleting `evals.yaml` before change #2 removes `evals/`** → Mitigation: harmless — the workflow simply ceases to exist; `evals/` source remains until change #2.
- **Re-locking pulls unrelated transitive bumps** → Mitigation: review the `uv.lock` diff; rely on the test suite; keep the change reviewable.

## Migration Plan

1. Update `pyproject.toml` (version bumps + bounds) → `uv lock` → run `ruff` + non-e2e tests → fix any FastMCP GA delta.
2. Add `.github/dependabot.yml`; delete `.github/workflows/evals.yaml`; add the CI gate to the publish workflow.
3. Apply repo-settings via `gh api` (Dependabot alerts, secret scanning + push protection, CodeQL default setup, delete `evals-and-secrets` environment); fall back to documented manual steps if unauthorized.
4. Add the `datacommons-client` observation contract test + the `diskcache` accepted-risk note.

**Rollback:** revert the change's commits (deps/CI/docs) and, for settings, re-toggle via `gh api` or the Settings UI. All steps are individually reversible; no data migration is involved.
