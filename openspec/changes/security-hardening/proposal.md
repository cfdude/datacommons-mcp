## Why

The public `datacommons-mcp` repo carries 22 real dependency CVEs (Critical in `fastmcp` and `authlib`), ships its core framework as a **beta** (`fastmcp>=3.0.0b1`, now superseded by GA 3.4.2), and has **Dependabot and secret scanning disabled** with **CodeQL in a broken "not-configured" state**. It also contains a `pull_request_target` workflow that checks out and executes untrusted PR code in a secret-bearing context — a textbook secret-exfiltration footgun that becomes live the moment any secret is added — and a PyPI publish workflow with **no test gate**. This is change #1 of the overhaul (see `docs/audits/2026-06-08-forensic-review.md`); security is sequenced first because it is the highest-severity, lowest-code-risk work and protects everything built afterward.

## What Changes

- **Resolve dependency CVEs.** Upgrade `fastmcp` off the beta to 3.x stable (`>=3.4,<4`), `authlib` to a patched release, and the remaining CVE'd packages (`cryptography`, `pyjwt`, `urllib3`, `requests`, `python-multipart`, `python-dotenv`, `pytest`, `pygments`); document `diskcache` (CVE-2025-69872, no fix published) as accepted-with-monitoring. Regenerate `uv.lock`. **BREAKING (build-time):** the FastMCP beta→GA jump may require code adjustments — validated by the existing test suite.
- **Bound all direct dependencies.** Add explicit `>=X,<NEXT_MAJOR` bounds to currently-unbounded deps (`requests`, `datacommons-client`, `pydantic-settings`) and pin `datacommons-client` (the observation-data contract — see the live-API analysis silent-failure risk).
- **Enable supply-chain scanning.** Add `.github/dependabot.yml` (uv + github-actions ecosystems); enable Dependabot alerts; enable secret scanning + push protection; fix CodeQL to a configured state so the 4 stale-but-already-fixed alerts auto-close; and pin the mutable `cfdude/.github@main` reusable-workflow refs in `security.yml` to immutable SHAs.
- **Remove the secret-exfiltration footgun.** Delete the `pull_request_target` eval workflow (the eval suite is non-functional and slated for deletion in change #2) and remove the orphan `evals-and-secrets` GitHub Environment (0 secrets, 0 protection rules).
- **Gate the release.** Make the PyPI publish workflow depend on CI (lint + tests) passing before `uv build`/`uv publish`.

Non-goals (explicitly out of scope): no SQLAlchemy/Alembic/FastAPI; no code refactor; no dead-code deletion beyond the insecure `evals.yaml` workflow (the rest is change #2).

## Capabilities

### New Capabilities
- `dependency-security`: version policy and CVE posture — no pre-release/beta in production, every direct dependency bounded, known CVEs resolved-or-documented, and `uv.lock` kept current and reproducible.
- `supply-chain-scanning`: automated detection controls for a public repo — Dependabot alerts + version-update config, secret scanning with push protection, and a correctly-configured CodeQL setup that closes stale alerts.
- `ci-release-safety`: CI/CD trust boundary — no workflow executes untrusted code in a secret-bearing context, no orphan deployment environments, and releases are gated on passing CI.

### Modified Capabilities
<!-- None — openspec/specs/ is empty; this is the first set of capabilities. -->

## Impact

- **Dependencies:** `pyproject.toml` (bounds + version bumps), `uv.lock` (regenerated). Possible minor code changes for the FastMCP beta→GA API delta, caught by `tests/`.
- **CI/workflows:** new `.github/dependabot.yml`; delete `.github/workflows/evals.yaml`; modify `.github/workflows/build-and-publish-datacommons-mcp.yaml` (CI gate) and `.github/workflows/security.yml` (SHA-pin reusable-workflow refs). `ci.yaml` unchanged here.
- **Repo settings (admin, via `gh api`):** enable Dependabot alerts, secret scanning + push protection, CodeQL default setup; delete the `evals-and-secrets` environment.
- **Coordination:** change #2 (`sever-upstream-deadweight`) deletes `evals/` itself; deleting `evals.yaml` here is forward-compatible with that.
- **Risk:** low code risk; the main validation surface is the FastMCP GA upgrade against the existing test suite (223 passing).
