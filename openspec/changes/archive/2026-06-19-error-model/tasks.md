## 1. Make masking explicit + add the input-validation exception

- [x] 1.1 In `servers/base.py`, set `mask_error_details=True` on the `FastMCP(...)` instance (the default is `False`, currently leaking raw error text to clients).
- [x] 1.2 In `exceptions.py`, add `class InvalidInputError(_ErrorStrMixin, ValueError)` (raised for client-caused input validation).

## 2. Add the error boundary + delete dead helpers

- [x] 2.1 Add `tool_error_boundary()` context manager to `servers/common.py`. Order: `except ToolError: raise`; then `except (InvalidInputError, DataLookupError, NoDataFoundError, InvalidDateFormatError, InvalidDateRangeError) as e: raise ToolError(str(e)) from e`; then `except Exception as e: logger.exception(...); raise ToolError("An internal error occurred while processing the request.") from e`. Import `ToolError` from `fastmcp.exceptions`, the domain exceptions from `..exceptions`, and add a module `logger = logging.getLogger(__name__)`. **Catch the explicit tuple, NOT broad `ValueError`/`LookupError`** (else pydantic `ValidationError`/`KeyError`/`IndexError` would leak).
- [x] 2.2 Delete the dead helpers from `servers/common.py`: `format_api_error`, `format_timestamp`, `get_output_handler`, `extract_output_options`, `OutputOptions`. Keep `get_client`, `get_config`. Trim now-unused imports (`datetime as dt`, `dataclass`, `Any`, the `OutputHandler` TYPE_CHECKING import) and set `__all__` to `["get_client", "get_config", "tool_error_boundary"]`.
- [x] 2.3 In `servers/__init__.py`, remove the 5 dead names from BOTH the `from .common import (...)` block and `__all__` (it currently re-exports all five — deleting them from common.py alone would ImportError). Add `tool_error_boundary` to the re-exports/`__all__` if the package root should expose it.

## 3. Convert the service's input validation

- [x] 3.1 In `services/observations.py`, change the 3 bare `raise ValueError(...)` (missing `variable_dcid`; place_name/place_dcid; date-range) to `raise InvalidInputError(...)` — messages unchanged. Import `InvalidInputError` from `..exceptions`.
- [x] 3.2 In `services/search.py`, change the 2 bare `raise ValueError(...)` (`per_search_limit`; `places`/`parent_place`) to `raise InvalidInputError(...)` — messages unchanged.

## 4. Apply the boundary at both tools + drop stderr

- [x] 4.1 `servers/observations.py`: wrap the `get_observations` body in `with tool_error_boundary():`; remove the catch-all `except Exception` (logger+`print(stderr)`+bare-raise); remove `import sys` if now unused.
- [x] 4.2 `servers/search.py`: wrap the `search_indicators` body in `with tool_error_boundary():`; replace the two `print(..., file=sys.stderr)` in the `places` fallback with the existing module `logger.debug(...)` (or `await ctx.debug(...)`); remove `import sys` if now unused.

## 5. Tests

- [x] 5.1 Add `tests/test_error_boundary.py` (CM unit tests): (a) each domain exception (`InvalidInputError`, `DataLookupError`, `NoDataFoundError`, `InvalidDateFormatError`, `InvalidDateRangeError`) raised inside → `ToolError` with the same message; (b) a pydantic `ValidationError` AND a `KeyError`/`IndexError` raised inside → generic `ToolError` whose message does NOT contain the original text, with the original chained as `__cause__` (proves no leak); (c) a `ToolError` raised inside → re-raised unchanged.
- [x] 5.2 Add an integration test via `async with Client(mcp)`: (a) invoking a tool with input that triggers `InvalidInputError` → the client-visible `ToolError` text contains the validation message; (b) a monkeypatched unexpected `RuntimeError("internal detail")` in the path → client receives the generic message and `"internal detail"` is absent.
- [x] 5.3 Verify the existing service `pytest.raises(ValueError, match=...)` tests still pass unchanged (`InvalidInputError` is a `ValueError`; messages unchanged).

## 6. Verification & integration

- [x] 6.1 No residue: `rg "file=sys.stderr|format_api_error|format_timestamp|get_output_handler|extract_output_options|OutputOptions" datacommons_mcp/` → none; `rg "import sys" datacommons_mcp/servers/` → none (unless used elsewhere).
- [x] 6.2 `rg "tool_error_boundary" datacommons_mcp/servers/` → observations.py + search.py; `rg "mask_error_details" datacommons_mcp/servers/base.py` → present.
- [x] 6.3 Final gate: `uv run ruff format --check && uv run ruff check && uv run pytest -m "not e2e"` → all pass (new tests added, no existing test dropped); `uv lock --check` consistent; server boots via `python datacommons_mcp/run_server.py` (EOF) with both tools registered.
- [x] 6.4 Commit per logical group (conventional commits), then proceed to Gate 2 (Superpowers code review) before finalizing.
