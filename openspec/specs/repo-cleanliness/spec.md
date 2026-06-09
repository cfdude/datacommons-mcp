# repo-cleanliness Specification

## Purpose
TBD - created by archiving change sever-upstream-deadweight. Update Purpose after archive.
## Requirements
### Requirement: No Google ADK / Gemini coupling
The repository SHALL NOT contain code that depends on the Google Agent Development Kit (`google.adk`) or Gemini — this is upstream-fork weight that is non-functional in this MCP server.

#### Scenario: ADK eval suite and sample agents are removed
- **WHEN** the repository tree is inspected
- **THEN** `evals/` and `examples/` are absent

#### Scenario: No google.adk imports remain
- **WHEN** the source tree is searched for `google.adk` / `google-adk` imports
- **THEN** none are found

### Requirement: No dead or orphaned files
The repository SHALL NOT retain modules with zero importers, loose root-level manual scripts, or process artifacts.

#### Scenario: Dead module and stray files are removed
- **WHEN** the repository is inspected
- **THEN** `datacommons_mcp/data_models/charts.py` (zero importers), `functional_test.py` (root-level manual script), and `SPRINT_2_INTEGRATION.md` are absent

#### Scenario: Removing the dead module does not break imports
- **WHEN** the package is imported and the test suite runs after `charts.py` removal
- **THEN** there are no import errors and all non-e2e tests pass

### Requirement: Runtime output is not tracked in version control
Generated runtime data (CSV/JSON exports) SHALL NOT be committed, and its output directory SHALL be git-ignored.

#### Scenario: Committed runtime CSV is removed and ignored
- **WHEN** `git ls-files datacommons-data/` is run and `.gitignore` is inspected
- **THEN** no files under `datacommons-data/` are tracked, and `.gitignore` excludes `datacommons-data/`

### Requirement: Documentation has no references to removed features
Documentation SHALL NOT reference removed capabilities (ADK/Gemini agents, the eval suite), leaving no dangling instructions.

#### Scenario: Docs are free of ADK/Gemini/eval references
- **WHEN** `README.md`, `docs/quickstart.md`, `docs/user_guide.md`, `docs/extension-compatibility.md`, and `docs/internal/evals.md` are inspected
- **THEN** they contain no instructions or references that depend on the deleted ADK/Gemini code or `evals/` suite (sections are trimmed or removed, with no broken links/paths)

