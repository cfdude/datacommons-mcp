## Why

Errors reach MCP clients inconsistently, and — verified empirically through an in-memory `Client(mcp)` against this repo's actual config — the current behavior is the **opposite of "safely masked"**: FastMCP's `mask_error_details` defaults to **False** and `base.py` never sets it, so **every** exception's raw message currently leaks to the client. A bare `ValueError` arrives wrapped and noisy (`Error calling tool 'X': <msg>`), and an unexpected `RuntimeError("internal secret…")` leaks its raw text too. On top of that: the `get_observations` tool wraps its body in a catch-all `except Exception` that logs, **prints to stderr**, and bare-re-raises; `search_indicators` has no error boundary and uses `print(..., file=sys.stderr)` for a `places` fallback parse; `format_api_error` and four other `common.py` helpers (`format_timestamp`, `get_output_handler`, `extract_output_options`, `OutputOptions`) are dead (zero prod/test refs); and `ToolError` is used nowhere.

So the real goals are: **(1)** surface clean, actionable messages for validation/domain failures, and **(2)** stop leaking internal error details (pydantic `ValidationError`, `KeyError`/`IndexError` from upstream-response parsing, arbitrary bugs). This is slice 4b of the decomposed `modularize-core` (#4) — small and isolated, intentionally landed **before** the high-risk search migration (4c).

## What Changes

- **Set masking explicitly.** Set `mask_error_details=True` on the FastMCP instance in `base.py` so correctness no longer rides on an unstated library default — anything that reaches FastMCP as a non-`ToolError` is masked.
- **Introduce one tool error boundary.** Add a reusable, unit-testable context manager that maps the **explicit domain-exception tuple** (`InvalidInputError`, `DataLookupError`, `NoDataFoundError`, `InvalidDateFormatError`, `InvalidDateRangeError`) → client-visible `ToolError(message)`; passes an existing `ToolError` through unchanged; and logs any other exception then raises a generic `ToolError`. **The catch is the explicit tuple, NOT broad `ValueError`/`LookupError`** — so pydantic `ValidationError` (a `ValueError` subclass) and `KeyError`/`IndexError` from response parsing are masked, not leaked.
- **Type the service's input validation.** Add `InvalidInputError(_ErrorStrMixin, ValueError)` to `exceptions.py` and convert the service's ~5 bare `raise ValueError(...)` (same messages) to it, so those validation messages are surfaced cleanly by the explicit-tuple boundary. Because `InvalidInputError` subclasses `ValueError`, the existing `pytest.raises(ValueError, match=...)` service tests stay green.
- **Apply the boundary at both tools** (`get_observations`, `search_indicators`); replace the `get_observations` catch-all stderr/bare-raise block and the `search_indicators` `places` stderr prints.
- **Replace `stderr` with logging/`ctx`.** Remove every `print(..., file=sys.stderr)` and the now-unused `import sys`; use the existing module `logger`/`ctx.debug`.
- **Delete dead scaffolding from BOTH `common.py` and `servers/__init__.py`.** Remove `format_api_error`, `OutputOptions`, `get_output_handler`, `extract_output_options`, `format_timestamp` (and their re-exports/`__all__` entries in `servers/__init__.py`, which currently re-exports all five). Keep `get_client`/`get_config`.

**CLIENT-VISIBLE behavior change:** validation/domain errors surface as clean actionable `ToolError` messages; internal errors are now masked (they leak today). No env/output/tool-signature changes.

Non-goal relaxation: this DOES make a scoped service-layer edit (bare `ValueError`→`InvalidInputError`, messages unchanged) — required to surface validation cleanly without leaking pydantic/`KeyError` internals. No other service logic changes.

## Capabilities

### New Capabilities
- `consistent-error-model`: the MCP tools surface errors through one consistent boundary — domain/validation failures reach the client as actionable `ToolError` messages, unexpected failures are logged and masked behind a generic `ToolError`, no tool writes to stderr, and dead error/helper scaffolding is removed.

### Modified Capabilities
<!-- None — error handling was not covered by the existing specs. -->

## Impact

- **Code:** `base.py` (`mask_error_details=True`); new `tool_error_boundary()` in `servers/common.py`; `servers/observations.py` + `servers/search.py` (apply boundary, drop stderr + `import sys`); `servers/common.py` AND `servers/__init__.py` (delete 5 dead helpers + trim imports/`__all__`/re-exports); `exceptions.py` (+`InvalidInputError`); `services/observations.py` + `services/search.py` (~5 `ValueError`→`InvalidInputError`, messages unchanged).
- **Tests:** add CM unit tests (each domain exception → `ToolError` message; pydantic `ValidationError` and `KeyError` → masked generic, NOT surfaced; existing `ToolError` passes through) **and** an integration test via `async with Client(mcp)` (a domain failure surfaces its actionable message; an unexpected `RuntimeError` is masked to the generic message). Existing service `pytest.raises(ValueError, ...)` tests stay green (`InvalidInputError` is a `ValueError`).
- **Risk:** medium — client-visible change, but the mapping is small, centralized, and tested both in isolation and through `Client(mcp)`. Suite + server boot are the gate.
