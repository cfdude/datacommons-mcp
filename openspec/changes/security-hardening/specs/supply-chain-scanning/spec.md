## ADDED Requirements

### Requirement: Dependabot is enabled with version-update configuration
The repository SHALL have Dependabot alerts enabled and SHALL include a `.github/dependabot.yml` that configures automated version-update PRs for both the Python dependency ecosystem and GitHub Actions.

#### Scenario: Dependabot config exists and covers both ecosystems
- **WHEN** `.github/dependabot.yml` is inspected
- **THEN** it declares `version: 2` with update entries for the Python package ecosystem (uv/pip) at `/` and for `github-actions` at `/`, each on a defined schedule

#### Scenario: Dependabot alerts are enabled on the repository
- **WHEN** the repository's security-and-analysis settings are queried
- **THEN** Dependabot alerts report as enabled (no longer "disabled")

### Requirement: Secret scanning and push protection are enabled
The public repository SHALL have secret scanning and secret-scanning push protection enabled.

#### Scenario: Secret scanning is active
- **WHEN** the repository's security-and-analysis settings are queried
- **THEN** `secret_scanning` and `secret_scanning_push_protection` both report as enabled

### Requirement: CodeQL is configured and stale alerts are cleared
CodeQL SHALL be in a configured (not "not-configured") state so it actively scans and so the 4 stale alerts — already remediated in code at commit `9b20adf` — auto-close on the next scan.

#### Scenario: CodeQL default setup is configured
- **WHEN** the CodeQL setup state is queried
- **THEN** it reports a configured state (default or advanced) for the `actions` and `python` languages, not "not-configured"

#### Scenario: Stale alerts close after re-scan
- **WHEN** CodeQL completes a scan against current `main`
- **THEN** the 4 previously-open alerts (workflow-permissions and unpinned-tag, all already fixed in code) are closed/fixed, not re-reported

### Requirement: Workflow references are pinned to immutable SHAs
GitHub Actions and reusable-workflow references SHALL be pinned to immutable commit SHAs (not mutable tags/branches like `@main`), so a third party cannot alter executed CI behavior after review.

#### Scenario: Reusable security workflows are SHA-pinned
- **WHEN** `.github/workflows/security.yml` is inspected
- **THEN** its `cfdude/.github/...` reusable-workflow references are pinned to commit SHAs (with a human-readable `# <ref>` comment), not `@main`
