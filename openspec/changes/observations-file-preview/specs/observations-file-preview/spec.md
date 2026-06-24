## ADDED Requirements

### Requirement: File-mode results include a bounded preview
When `get_observations` returns a file-mode result, it SHALL include a bounded sample of the data so the agent can see the content without opening the file.

#### Scenario: A large result includes the first N rows
- **WHEN** `get_observations` returns an `ObservationsFileResult`
- **THEN** its `preview` contains the first N (default 10) flattened observation rows as typed `ObservationPreviewRow`s (place dcid/name/type, variable dcid/name, date, value, source_id), and the full dataset is still written only to the file

#### Scenario: The preview is bounded
- **WHEN** the underlying result has more than N rows
- **THEN** `preview` contains exactly N rows (never the full dataset); when it has ≤ N rows, `preview` contains all of them

### Requirement: File-mode results carry summary metadata
The file-mode result SHALL carry enough metadata for an agent to describe the export without opening the file.

#### Scenario: Summary states totals and location
- **WHEN** an `ObservationsFileResult` is returned
- **THEN** it includes `columns` (the CSV column headers), `variable_name`, and a `summary` string that states the total rows written (`rows_written`), the file path, and that a sample is shown — e.g. covering "N rows written to `<path>`; showing the first K; full file at `<path>`"

#### Scenario: rows_written is the authoritative total
- **WHEN** the summary cites a record count
- **THEN** it uses `rows_written` (the true total written; no `truncated`/`total_available` fields are added, as nothing is truncated)

### Requirement: Screen-mode and streaming behavior are unchanged
The preview SHALL be additive and SHALL NOT change other behavior.

#### Scenario: Screen mode is untouched
- **WHEN** `get_observations` returns an `ObservationsScreenResult` (small result)
- **THEN** it is unchanged (no preview fields; the data is already inline)

#### Scenario: No change to what goes to disk or memory
- **WHEN** a file is produced
- **THEN** the same full dataset is written to the file as before, and the preview is taken from the already-materialized response (no extra fetch, no second pass)

### Requirement: Suite and server stay green
The change SHALL keep the suite green and pin the new file-result shape.

#### Scenario: Tests assert the preview contract
- **WHEN** the test suite runs
- **THEN** handler-level tests assert `preview`/`columns`/`variable_name`/`summary` on a file result, a `Client(mcp)` test asserts they appear in the tool's structured output, and the full non-e2e suite passes
