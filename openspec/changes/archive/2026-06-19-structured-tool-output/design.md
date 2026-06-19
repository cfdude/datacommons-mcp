## Context

A live `Client(mcp)` probe (FastMCP 3.4.2) confirmed both tools advertise `{"type":"object","additionalProperties":true}` — no field-level contract. `search_indicators` already builds `SearchResponse` then flattens it (`servers/search.py:326` `model_dump(exclude_none=True)`). `get_observations` returns a hand-built dict from `OutputHandler.handle_observations` with two branches: screen (`{output_mode:"screen", data: ObservationToolResponse.model_dump()}`) and file (`PaginationResult.to_dict()` + `format`/`multi_file`), decided by `screen_row_threshold` / pagination (`utils/output_handler.py`). The server runs as a local stdio subprocess, so the file branch's server-side path is genuinely usable by the user.

## Goals / Non-Goals

**Goals:** both tools return typed, schema-bearing structured output; data shapes unchanged (typing only); docstring made truthful.

**Non-Goals:** CSV-write performance; a data preview/sample in the file response; converting the file branch from path → inlined content; changing the screen/file threshold.

## Decisions

**1. `get_observations` → discriminated union `ObservationsScreenResult | ObservationsFileResult` (discriminated on `output_mode`).** Rationale: the two outcomes are genuinely different shapes; a union models them honestly with no cross-branch null fields. The user's deployment dissolves the usual objections: (a) consumer is an LLM, so FastMCP nesting a top-level union under a `result` key in `structured_content` is immaterial; (b) local stdio means the file path is real and usable; (c) the file branch returns only metadata (path, counts) — the rows stream to CSV — so structured output never bloats the response. *Alternative (single flat model with all-optional branch fields):* rejected — preserves the exact flat wire shape but pollutes every response with the other branch's null fields and gives a weaker schema; the wire-shape preservation has no value when the consumer is an LLM.

**2. The `OutputHandler` builds and returns the models directly** (not dicts re-wrapped at the tool). `_build_screen_response` returns `ObservationsScreenResult`; `_handle_file_output` returns `ObservationsFileResult` (replacing `PaginationResult.to_dict()` at the tool boundary — `PaginationResult` the dataclass can stay internal, or map into the model). End-to-end typing; the tool just returns the handler's value. *Alternative (tool re-wraps the dict):* rejected — builds a dict then re-parses it, leaving the handler untyped.

**3. `search_indicators` → return `SearchResponse` directly.** Annotate `-> SearchResponse`, `return response`, drop `model_dump(exclude_none=True)`.

**4. Accept per-schema nulls AND alias-cased keys (drop manual `exclude_none`).** Returning models means FastMCP serializes them itself: (a) without the old `exclude_none`, so previously-omitted optionals appear as `null` (e.g. `topics: null` in lookup mode; optional `Node`/`FacetMetadata` fields); and (b) **with `by_alias=True`** (FastMCP's structured-output default, verified on 3.4.2), so aliased keys serialize by alias — `type_of`→`typeOf`, `import_name`→`importName`, `measurement_method`→`measurementMethod`, `observation_period`→`observationPeriod`, `provenance_url`→`provenanceUrl`. Today's manual `model_dump(exclude_none=True)` emits the snake_case field names. Both are deliberate, schema-consistent wire refinements (the generated schema uses the same aliases, so content validates against schema), not data-value changes; the alias casing also matches Data Commons' own API field naming. There is no clean per-tool way to force snake_case under FastMCP, and the alias form is the better contract — so we accept it rather than fight it.

**5. Reuse `ObservationToolResponse` unchanged** as the screen branch's `data`. New models live in `data_models/observations.py` (file result) and reference the search models as-is.

## Risks / Trade-offs

- **Client-visible output shape changes** (real schemas; union `result` nesting; per-schema nulls) → Mitigation: intended and documented; consumer is an LLM; a `Client(mcp)` test pins the new schema; data values unchanged.
- **Handler-level tests assert dict keys** → Mitigation: update them to model attributes (mechanical); they already construct the handler directly so they exercise the real builders.
- **`PaginationResult.to_dict()` consumers** → only the file branch + its unit test; map into the model and update the test.

## Migration Plan

1. `data_models/observations.py`: add `ObservationsScreenResult` and `ObservationsFileResult` (discriminated on `output_mode`); reuse `ObservationToolResponse`.
2. `utils/output_handler.py` (+ `pagination_handler.py`): `_build_screen_response`/`_handle_file_output` return the new models; `handle_observations` return type becomes the union.
3. `servers/observations.py`: `-> ObservationsScreenResult | ObservationsFileResult`; truthful docstring.
4. `servers/search.py`: `-> SearchResponse`; `return response`.
5. Tests: update handler-level e2e/integration + pagination tests to model attributes; add `Client(mcp)` schema/output tests for both tools.
6. Gate: ruff + non-e2e suite + server boot + both-tools-register; optional live smoke if a key is present.

**Rollback:** revert the commits; no data/migration involved.
