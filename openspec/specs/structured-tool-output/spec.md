# structured-tool-output Specification

## Purpose
TBD - created by archiving change structured-tool-output. Update Purpose after archive.
## Requirements
### Requirement: search_indicators returns typed structured output
The `search_indicators` tool SHALL declare and return the `SearchResponse` model so FastMCP advertises a field-level output schema, instead of returning an untyped `dict`.

#### Scenario: The tool returns the SearchResponse model
- **WHEN** `search_indicators` completes
- **THEN** it returns a `SearchResponse` instance (the tool is annotated `-> SearchResponse` and no longer hand-serializes via `model_dump`)

#### Scenario: The advertised output schema is field-level
- **WHEN** a client inspects the `search_indicators` output schema (e.g. via `Client(mcp).list_tools()`)
- **THEN** the schema describes `SearchResponse`'s fields (topics, variables, dcid_name_mappings, dcid_place_type_mappings, resolved_parent_place, status) and is NOT `{"type": "object", "additionalProperties": true}`

### Requirement: get_observations returns a typed screen/file discriminated union
The `get_observations` tool SHALL return one of two typed models discriminated on `output_mode`: an inline-data result or a file-reference result. The underlying data shapes (which fields, when) SHALL be unchanged — only typed.

#### Scenario: Small response returns the screen model with inline data
- **WHEN** the response is within the screen-row threshold (and not paginated)
- **THEN** the tool returns an `ObservationsScreenResult` with `output_mode == "screen"` and `data` being the `ObservationToolResponse` (variable, place_observations, source_metadata, etc.)

#### Scenario: Large or paginated response returns the file model with a path
- **WHEN** the response exceeds the screen-row threshold or is paginated
- **THEN** the tool returns an `ObservationsFileResult` with `output_mode == "file"`, a `file_path` to the written export, `format` (`"csv"` by default), and the export metadata (`rows_written`, `pages_fetched`, `file_size_bytes`, `unique_places_count`); the observation rows are NOT inlined in the response

#### Scenario: The advertised output schema is field-level for both branches
- **WHEN** a client inspects the `get_observations` output schema
- **THEN** the schema describes the screen and file result shapes (discriminated on `output_mode`) and is NOT `{"type": "object", "additionalProperties": true}`

### Requirement: Data values and branch logic are preserved (typing only)
Introducing structured output SHALL NOT change which data the tools return or when — the screen/file decision, thresholds, CSV-default export, and field VALUES are unchanged. The serialized key representation MAY change as a documented consequence of typed serialization (optional fields appear as `null` rather than omitted; aliased keys serialize by alias, e.g. `type_of`→`typeOf`), and `get_observations`'s union payload is nested under `result` — but the schema and content remain mutually consistent.

#### Scenario: The screen/file decision and values are unchanged
- **WHEN** the same query is run before and after this change
- **THEN** it resolves to the same branch (screen vs file) by the same threshold/pagination logic, with the same field VALUES (now carried by typed models; keys follow the model aliases and nulls appear per-schema)

#### Scenario: The tool docstring matches the returned models
- **WHEN** the `get_observations` docstring describes the file-mode result
- **THEN** it lists the fields actually present on `ObservationsFileResult` (including `format`, and the optional `multi_file`/`companion_files`), not a stale subset

### Requirement: The suite and server validate the new contract
The change SHALL keep the suite green and add a client-level assertion of the new schemas.

#### Scenario: Client-level schema/output test passes
- **WHEN** the `Client(mcp)` test suite runs
- **THEN** it asserts both tools advertise field-level output schemas and that returned structured content validates against them

#### Scenario: Suite and server stay green
- **WHEN** the full non-e2e suite runs and the stdio server boots
- **THEN** all non-e2e tests pass (handler-level tests updated to the typed models) and the server starts with both tools registered

