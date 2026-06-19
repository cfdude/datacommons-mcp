## ADDED Requirements

### Requirement: Error detail masking is set explicitly
The FastMCP server SHALL explicitly enable error-detail masking rather than relying on the library default (which is `False`, currently leaking raw internal error messages to clients).

#### Scenario: Masking is configured on the server
- **WHEN** the FastMCP server instance is created in `base.py`
- **THEN** `mask_error_details=True` is set explicitly (so any non-`ToolError` reaching FastMCP is masked, independent of the library default)

### Requirement: Domain and validation errors reach the client as ToolError
Failures from a known domain exception SHALL be surfaced to the client as a `fastmcp.exceptions.ToolError` carrying the original actionable message. The boundary SHALL catch the EXPLICIT domain-exception tuple — `InvalidInputError`, `DataLookupError`, `NoDataFoundError`, `InvalidDateFormatError`, `InvalidDateRangeError` — NOT the broad `ValueError`/`LookupError` base classes.

#### Scenario: A domain exception is mapped to a client-visible ToolError
- **WHEN** code inside the tool error boundary raises one of the explicit domain exceptions
- **THEN** the boundary raises a `ToolError` whose message equals the original exception's message, chained from the original

#### Scenario: An invalid tool argument surfaces an actionable message to a real client
- **WHEN** a tool is invoked via an in-memory `Client(mcp)` with input the service rejects (e.g. missing `variable_dcid` → `InvalidInputError`)
- **THEN** the client receives a `ToolError` whose text contains the specific validation message

### Requirement: Internal and unexpected errors are masked, never leaked
Exceptions that are NOT in the explicit domain tuple SHALL be logged and surfaced as a generic `ToolError` that does not contain the original message — including `ValueError`/`LookupError` subclasses that are NOT domain exceptions (pydantic `ValidationError`, `KeyError`, `IndexError`).

#### Scenario: A non-domain ValueError/LookupError subclass is masked
- **WHEN** code inside the boundary raises a pydantic `ValidationError` (a `ValueError` subclass) or a `KeyError`/`IndexError` (`LookupError` subclasses) from internal parsing
- **THEN** the boundary logs it and raises a generic `ToolError` whose message does NOT include the original error text (no internal leak), chained via `__cause__`

#### Scenario: An unexpected error is masked end-to-end
- **WHEN** a tool invoked via `Client(mcp)` hits an unexpected `RuntimeError("internal detail")`
- **THEN** the client receives the fixed generic message and the string `"internal detail"` is absent from the client-visible error

#### Scenario: An existing ToolError passes through unchanged
- **WHEN** code inside the boundary raises a `ToolError` directly
- **THEN** it is re-raised unchanged (not re-wrapped or masked)

### Requirement: Tools do not write to stderr
The tool layer SHALL use structured logging / the FastMCP `Context`, not `print(..., file=sys.stderr)`.

#### Scenario: No stderr prints remain in the tool layer
- **WHEN** `datacommons_mcp/servers/observations.py` and `datacommons_mcp/servers/search.py` are inspected
- **THEN** they contain no `print(..., file=sys.stderr)` calls and no longer import `sys` for that purpose

### Requirement: Dead error and helper scaffolding is removed
Unused error/helper code SHALL be deleted from every module that defines or re-exports it.

#### Scenario: Dead helpers are gone from definition and re-export sites
- **WHEN** `datacommons_mcp/servers/common.py` and `datacommons_mcp/servers/__init__.py` are inspected
- **THEN** `format_api_error`, `format_timestamp`, `get_output_handler`, `extract_output_options`, and `OutputOptions` are absent from both the definitions and the `__init__` re-exports/`__all__` (each verified zero prod/test refs), while `get_client` and `get_config` remain

### Requirement: Service behavior stays compatible
The service layer's input-validation conversion (bare `ValueError` → `InvalidInputError`) SHALL preserve the existing exception contract.

#### Scenario: Service-layer error tests still pass
- **WHEN** the existing service tests that assert `pytest.raises(ValueError | DataLookupError | InvalidDateFormatError | InvalidDateRangeError, match=...)` run after this change
- **THEN** they pass unchanged (because `InvalidInputError` subclasses `ValueError` and the messages are unchanged)

#### Scenario: Suite and server stay green
- **WHEN** the full non-e2e suite runs and the stdio server boots after this change
- **THEN** all non-e2e tests pass and the server starts and registers both tools without error
