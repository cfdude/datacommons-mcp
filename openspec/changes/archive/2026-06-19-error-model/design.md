## Context

Verified empirically through an in-memory `Client(mcp)` against this repo's config: `fastmcp.settings.mask_error_details` defaults to **False** and `base.py` never overrides it, so **all** exception messages currently leak to clients (a raw `RuntimeError` text reaches the client; validation `ValueError`s arrive wrapped/noisy). The service raises domain exceptions (`DataLookupError`, `NoDataFoundError`, `InvalidDateFormatError`, `InvalidDateRangeError` — all subclass `LookupError`/`ValueError`) plus ~5 bare `ValueError`s for input validation. `format_api_error` + 4 other `common.py` helpers are dead (zero refs) and are re-exported by `servers/__init__.py`. No tool-boundary error tests exist. This is the small, isolated slice 4b, before the high-risk search migration (4c).

## Goals / Non-Goals

**Goals:**
- One consistent, unit- and integration-tested error boundary; domain/validation errors reach clients as clean `ToolError` messages; everything else is masked + logged; no stderr; dead scaffolding removed; masking made explicit.

**Non-Goals:**
- No search migration (4c), no clients.py split (4c), no structured output (4d), no exceptions.py vocabulary changes BEYOND adding `InvalidInputError`.
- The ONLY service-layer edit is the scoped bare-`ValueError`→`InvalidInputError` conversion (messages unchanged); no other service logic changes.

## Decisions

**1. Set `mask_error_details=True` explicitly in `base.py`.** Don't let masking ride on an unstated library default (currently `False`). Belt-and-suspenders with Decision 3 (the boundary already converts everything to `ToolError`), but it documents intent and protects any non-boundary path.

**2. Catch the EXPLICIT domain-exception tuple, NOT broad `ValueError`/`LookupError`.** Broad catching would surface pydantic `ValidationError` (a `ValueError` subclass) and `KeyError`/`IndexError` (from `clients.py`'s raw response subscripting) to clients — an internal leak. The boundary catches exactly `(InvalidInputError, DataLookupError, NoDataFoundError, InvalidDateFormatError, InvalidDateRangeError)`. *Alternative (broad catch + accept the leak):* rejected — leaking pydantic/KeyError text defeats the purpose of an "error model" change.

**3. Type the service's input validation as `InvalidInputError`.** Add `InvalidInputError(_ErrorStrMixin, ValueError)` and convert the ~5 bare `raise ValueError(...)` in `services/observations.py` (:56/59/73) and `services/search.py` (:214/217) to it (messages unchanged). This lets the explicit-tuple boundary surface them WITHOUT broadening the catch. Because `InvalidInputError` is a `ValueError`, the existing `pytest.raises(ValueError, match=...)` service tests keep passing, and `_ErrorStrMixin` keeps the message substring intact for `match=` (it only prepends the class name).

**4. Boundary = a sync context manager `tool_error_boundary()` in `servers/common.py`.** Mapping (order matters):
```
except ToolError:                          raise                                  # pass through
except (InvalidInputError, DataLookupError, NoDataFoundError,
        InvalidDateFormatError, InvalidDateRangeError) as e:
                                           raise ToolError(str(e)) from e          # surface
except Exception as e:                     logger.exception(...); raise ToolError(GENERIC) from e   # mask
```
`ToolError.__mro__` does not include `ValueError`/`LookupError` (verified), so the pass-through guard is sufficient. A sync CM around an `async` tool body is correct — exceptions from awaited calls propagate to `__exit__` normally. `GENERIC = "An internal error occurred while processing the request."`. Tools surface messages via `str(e)` (the `_ErrorStrMixin` form, e.g. `"DataLookupError: …"`).

**5. Logging instead of stderr.** Replace `get_observations`'s catch-all/`print`/bare-raise with the boundary; replace `search_indicators`'s `places`-fallback `print(stderr)` with the **existing** module `logger.debug` (search.py already has a module logger) or `await ctx.debug(...)`. Remove `import sys` from both files.

**6. Delete dead helpers from BOTH `common.py` and `servers/__init__.py`** (the latter re-exports all five in its import block and `__all__`).

## Risks / Trade-offs

- **Over-mask a client-relevant error that isn't in the tuple** → Mitigation: the client-relevant vocabulary IS exactly the domain tuple; the service's only other client-facing errors (bare ValueErrors) are converted to `InvalidInputError`. Future client-facing errors must be domain exceptions.
- **`InvalidInputError` conversion breaks a `match=` test** → Mitigation: `_ErrorStrMixin` prepends only the class name; `pytest.raises(..., match=substring)` uses `re.search`, so the original message substring still matches. Verified pattern.
- **Double-wrapping/swallowing a `ToolError`** → Mitigation: explicit `except ToolError: raise` first; unit-test the pass-through.

## Migration Plan

1. `base.py`: set `mask_error_details=True` on the FastMCP instance.
2. `exceptions.py`: add `InvalidInputError(_ErrorStrMixin, ValueError)`.
3. `common.py`: add `tool_error_boundary()` + `ToolError` import + module `logger`; delete the 5 dead helpers + trim imports/`__all__`. `servers/__init__.py`: drop the 5 dead re-exports + `__all__` entries; add `tool_error_boundary` if it should be re-exported (else import from common directly in the tools).
4. `services/{observations,search}.py`: convert the ~5 bare `ValueError`→`InvalidInputError`.
5. `servers/{observations,search}.py`: wrap tool bodies in the boundary; remove stderr + `import sys`; search `places` fallback → `logger.debug`.
6. Tests: CM unit tests (domain→ToolError msg; pydantic `ValidationError` + `KeyError`→generic, no leak; `ToolError` pass-through) + integration test via `async with Client(mcp)` (domain→actionable; `RuntimeError`→masked generic, original text absent).
7. Gate: ruff + non-e2e suite + server boot.

**Rollback:** revert the commits; no data/migration involved.
