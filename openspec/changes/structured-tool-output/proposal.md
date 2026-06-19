## Why

Both MCP tools are annotated `-> dict` and hand-build/serialize plain dicts (`search_indicators` does `response.model_dump(exclude_none=True)`; `get_observations` returns the OutputHandler's hand-built dict). I verified against a live in-memory `Client(mcp)` (FastMCP 3.4.2) that this makes **both tools advertise a useless output schema** — `{"type": "object", "additionalProperties": true}`. Clients (Claude Desktop/Code, ChatGPT) get no field-level contract for what these tools return.

This is slice 4d of the decomposed `modularize-core`. `search_indicators` is trivial (it already builds a clean `SearchResponse` model). `get_observations` is the hard part: it returns a **polymorphic** result — inline data when small (`output_mode: "screen"`), or a CSV/JSON **file reference** when large or paginated (`output_mode: "file"`) — currently an untyped dict (+ a `PaginationResult` dataclass). The server runs locally (stdio subprocess under Claude Desktop), so the file path is a real, usable path on the user's machine — the file-reference design is correct and stays.

## What Changes

- **`search_indicators` returns a typed `SearchResponse`.** Change the annotation `-> dict` → `-> SearchResponse` and `return response` (drop the manual `.model_dump()`). FastMCP then generates a real output schema and structured content.
- **`get_observations` returns a typed discriminated union** `ObservationsScreenResult | ObservationsFileResult`, discriminated on the existing `output_mode` literal:
  - `ObservationsScreenResult`: `output_mode: Literal["screen"]`, `data: ObservationToolResponse` (reuses the existing model).
  - `ObservationsFileResult`: `output_mode: Literal["file"]`, `file_path`, `rows_written`, `pages_fetched`, `file_size_bytes`, `unique_places_count`, `format: Literal["csv","json"]`, plus the optional `companion_files`/`multi_file` that the runtime can emit.
  - The `OutputHandler` builds and returns these models directly (instead of hand-built dicts / `PaginationResult.to_dict()`), so typing is end-to-end.
- **Make the `get_observations` docstring truthful** — it currently lists 6 file-mode keys but the runtime emits up to 9 (`format`, `multi_file`, `companion_files` were undocumented). The models become the source of truth.

**CLIENT-VISIBLE change (intended):** both tools advertise real field-level output schemas instead of `additionalProperties: true`. Three consequences to accept, all appropriate for structured output and all immaterial to the LLM consumer (the only consumer): (a) FastMCP nests a top-level union under a `result` key in `structured_content` (so `get_observations`'s structured payload becomes `{"result": {...}}`); (b) optional fields previously omitted via `exclude_none` now appear per-schema (e.g. `topics: null` in lookup mode); (c) **FastMCP serializes structured content `by_alias=True`, so aliased keys move to their alias casing** — `type_of`→`typeOf`, `import_name`→`importName`, `measurement_method`→`measurementMethod`, `observation_period`→`observationPeriod`, `provenance_url`→`provenanceUrl` (today's `model_dump(exclude_none=True)` emits the snake_case field names). The schema and content are mutually consistent (both use the alias), so the contract is self-consistent; the alias casing also matches Data Commons' own API naming.

Non-goals (flagged, not bundled): NO CSV-write performance work (the file branch returns only metadata; the rows stream to the CSV — typing is orthogonal to write efficiency); NO data preview/sample in the file response (a behavior add, good fast-follow); NO change of the file branch from a path to inlined content (the local-stdio deployment makes the path correct); NO change to the screen/file threshold behavior.

## Capabilities

### New Capabilities
- `structured-tool-output`: both MCP tools return typed, schema-bearing structured output — `search_indicators` a `SearchResponse`, `get_observations` a discriminated union over its screen/file result shapes — so clients receive a real output contract instead of an open object.

## Impact

- **Code:** `servers/search.py` (return typed model), `servers/observations.py` (return type + truthful docstring), `utils/output_handler.py` + `utils/pagination_handler.py` (build/return the new models instead of dicts), `data_models/observations.py` (new `ObservationsScreenResult`/`ObservationsFileResult`, reusing `ObservationToolResponse`).
- **Tests:** handler-level e2e/integration tests assert dict keys (`result["output_mode"]`, `result["file_path"]`, `result["data"][...]`) — update to model attributes; `test_pagination_handler.py` (`PaginationResult.to_dict`); add `Client(mcp)` tests asserting the new `outputSchema` is field-level (not `additionalProperties: true`) and `structured_content` validates.
- **Risk:** MEDIUM (client-visible output contract). Mitigations: the data shapes are unchanged (only typed); a `Client(mcp)` schema test pins the new contract; the union faithfully covers both existing branches; local-stdio deployment verified so the file-path branch is correct.
