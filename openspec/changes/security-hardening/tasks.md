## 1. Dependency CVE remediation (`dependency-security`)

- [x] 1.1 Update `pyproject.toml`: change `fastmcp` to `>=3.4,<4` (off the `3.0.0b1` beta).
- [x] 1.2 Update `pyproject.toml`: add/raise bounds for `authlib` (transitive — pin floor `>=1.6.12` if declared, else rely on lock upgrade), `cryptography>=46.0.7`, and ensure `pyjwt`, `urllib3`, `python-multipart`, `python-dotenv`, `pygments` resolve to fixed versions.
- [x] 1.3 Add explicit `>=X,<NEXT_MAJOR` bounds to currently-unbounded direct deps: `requests`, `datacommons-client`, `pydantic-settings`.
- [x] 1.4 Bump dev dep `pytest` to `>=9.0.3,<10` (CVE-2025-71176) — raise the current `<9.0.0` cap; pytest 9 is a major bump, so let task 1.6's suite run catch any `pytest-asyncio`/`pytest-cov` compat breakage (re-lock those too if needed).
- [x] 1.5 Run `uv lock --upgrade-package fastmcp --upgrade-package authlib --upgrade-package cryptography --upgrade-package pyjwt --upgrade-package urllib3 --upgrade-package requests --upgrade-package python-multipart --upgrade-package python-dotenv --upgrade-package pytest --upgrade-package pygments` and review the `uv.lock` diff.
- [x] 1.6 Run `uv run ruff format --check && uv run ruff check && uv run pytest -m "not e2e"`; fix any FastMCP beta→GA API breakage (RED→GREEN). If a hard blocker, fall back to a bounded 2.x pin and document why.
- [x] 1.7 Verify with Trivy/`uv` that no runtime package carries a pre-release suffix and no Critical/High CVE remains except documented exceptions.

## 2. External-data contract guard (`dependency-security`)

- [x] 2.1 Add a contract test (e.g. `tests/test_observation_contract.py`) that parses `docs/audits/api-samples/v2-observation.json` through the `datacommons-client` observation models into `FacetMetadata`, asserting: (a) parse succeeds; (b) `import_name` and `provenance_url` map non-null for every facet; (c) the fully-populated facet `4181918134` maps all four lineage fields non-null. Do NOT assert the optional `measurement_method`/`observation_period` are present on all facets — they are legitimately absent on some (verified in the fixture: `observation_period` on 2/10, `measurement_method` missing on facet `2825511676`). The test guards the alias-mapping (the silent-`None` drift surface), not field presence.
- [x] 2.2 ~~Add an accepted-risk note for `diskcache` CVE-2025-69872 (no fix)~~ — **N/A: obsolete.** The `fastmcp` 3.0.0b1→3.4.0 upgrade removed `diskcache` from the dependency tree entirely (replaced by `py-key-value-aio`/`caio`), so the no-fix CVE no longer applies. Verified absent from `uv.lock`.

## 3. Supply-chain scanning config (`supply-chain-scanning`)

- [x] 3.1 Create `.github/dependabot.yml` with `version: 2` and update entries for the Python ecosystem (uv/pip) at `/` and `github-actions` at `/`, weekly, with grouped Python updates and `open-pull-requests-limit`.
- [x] 3.2 Enable Dependabot **alerts** via `gh api -X PUT repos/cfdude/datacommons-mcp/vulnerability-alerts`. **Done** (HTTP 204).
- [x] 3.3 Enable secret scanning + push protection via `gh api -X PATCH repos/cfdude/datacommons-mcp` with `security_and_analysis`. **Done** — both report `enabled`.
- [ ] 3.4 Enable CodeQL default setup for `actions` + `python`. **BLOCKED (manual admin step required):** the `PUT .../code-scanning/default-setup` API returns HTTP 404 despite a working `GET` and confirmed admin scope (3.2/3.3 succeeded) — GitHub's documented behavior when default setup must be enabled via the web UI. **User action:** Settings → Code security → Code scanning → "Default setup" → Enable (languages: Actions, Python). The 4 stale alerts (already fixed in code at `9b20adf`) will auto-close on the first scan.
- [x] 3.5 Pin the reusable workflow references in `.github/workflows/security.yml` (`cfdude/.github/...@main`, lines 13 & 19) to immutable commit SHAs (with a `# <ref>` comment), closing the mutable-ref supply-chain gap. **Done** — pinned to `6643615`.

## 4. CI/CD trust boundary (`ci-release-safety`)

- [ ] 4.1 Delete `.github/workflows/evals.yaml` (removes the `pull_request_target` + untrusted-checkout secret-exfiltration footgun).
- [ ] 4.2 Delete the `evals-and-secrets` GitHub Environment via `gh api -X DELETE repos/cfdude/datacommons-mcp/environments/evals-and-secrets` (or documented manual fallback); confirm no workflow references it.
- [ ] 4.3 Add an in-workflow lint+test gate job to `.github/workflows/build-and-publish-datacommons-mcp.yaml` and make the build/publish job `needs:` it, so a failing lint/test blocks publish.

## 5. Verification & integration

- [ ] 5.1 Re-run `gh api .../code-scanning/alerts?state=open` and confirm Trivy/CodeQL counts dropped to documented residual only.
- [ ] 5.2 Confirm `gh api .../environments` no longer lists `evals-and-secrets` and security-and-analysis settings report scanning enabled.
- [ ] 5.3 Final gate: `uv run ruff format --check && uv run ruff check && uv run pytest -m "not e2e"` all green; `uv lock` consistent with `pyproject.toml`.
- [ ] 5.4 Commit per-task (conventional commits, one logical change per commit), then proceed to Gate 2 (Superpowers code review) before any documentation update.
