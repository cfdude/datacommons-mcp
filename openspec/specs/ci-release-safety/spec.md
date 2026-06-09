# ci-release-safety Specification

## Purpose
TBD - created by archiving change security-hardening. Update Purpose after archive.
## Requirements
### Requirement: No workflow executes untrusted code in a secret-bearing context
No GitHub Actions workflow SHALL both (a) run in a context with access to repository/organization secrets and (b) check out and execute code from an untrusted pull request head. This eliminates the `pull_request_target` + untrusted-checkout secret-exfiltration class.

#### Scenario: The insecure eval workflow is removed
- **WHEN** `.github/workflows/` is inspected after this change
- **THEN** there is no workflow that triggers on `pull_request_target` while checking out `github.event.pull_request.head.sha` and injecting secrets into a run step

#### Scenario: No remaining pull_request_target workflow grants secret access to PR code
- **WHEN** every workflow triggering on `pull_request_target` is inspected
- **THEN** none executes attacker-controllable PR code with secrets in scope

### Requirement: No orphan deployment environments
The repository SHALL NOT retain GitHub Environments that exist only to imply a deployment, hold no secrets, and enforce no protection rules.

#### Scenario: The evals-and-secrets environment is deleted
- **WHEN** the repository's environments are listed
- **THEN** `evals-and-secrets` is no longer present

#### Scenario: No workflow references the deleted environment
- **WHEN** `.github/workflows/` is inspected
- **THEN** no workflow declares `environment: evals-and-secrets`

### Requirement: Releases are gated on passing CI
The PyPI publish workflow SHALL NOT build or publish unless CI checks (lint + tests) have passed for the same commit.

#### Scenario: Publish depends on CI
- **WHEN** the publish workflow (`build-and-publish-datacommons-mcp.yaml`) is inspected
- **THEN** the build/publish job runs only after a CI gate (lint + tests) succeeds for that commit — e.g. via a `needs:` dependency or an inline lint+test step that must pass before `uv build`/`uv publish`

#### Scenario: A failing build cannot publish
- **WHEN** lint or tests fail for a commit that bumps the version on `main`
- **THEN** the publish step does not run (no broken release reaches PyPI)

