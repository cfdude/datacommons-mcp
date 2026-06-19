## 1. Output models

- [ ] 1.1 In `data_models/observations.py`, add `ObservationsScreenResult` (`output_mode: Literal["screen"]`, `data: ObservationToolResponse`) and `ObservationsFileResult` (`output_mode: Literal["file"]`, `file_path: str | None`, `rows_written: int`, `pages_fetched: int`, `file_size_bytes: int`, `unique_places_count: int`, `format: Literal["csv","json"]`, `companion_files: dict[str,str] | None = None`, `multi_file: bool | None = None`). Define the type alias `ObservationsResult = ObservationsScreenResult | ObservationsFileResult` — a tagged union keyed on the `output_mode` literal (renders as `anyOf` with `const` tags; no JSON-Schema `discriminator` unless explicitly annotated, which is unnecessary).

## 2. Wire the OutputHandler to return models

- [ ] 2.1 `utils/output_handler.py::_build_screen_response` returns `ObservationsScreenResult(output_mode="screen", data=<ObservationToolResponse>)` (stop hand-building the dict / `.model_dump()`).
- [ ] 2.2 `utils/output_handler.py::_handle_file_output` returns `ObservationsFileResult(...)` populated from the `PaginationResult` fields (+ `format`, and `multi_file` only when requested). Compute `unique_places_count=len(pagination_result.unique_places)` (the dataclass stores the set, not a count). **RETAIN `PaginationResult.to_dict()`** as an internal helper (do NOT delete it) so its existing unit tests stay green; build the model from the dataclass fields (or from `to_dict()`).
- [ ] 2.3 `handle_observations` return type becomes `ObservationsResult` (the union); all branches return a model.

## 3. Type the tools

- [ ] 3.1 `servers/observations.py::get_observations`: annotate `-> ObservationsScreenResult | ObservationsFileResult`, return the handler's model, and rewrite the docstring's **"Returns" section** (currently lists only 6 file-mode keys) to match the models — include `format`, `multi_file`, `companion_files` and describe both the screen and file branches accurately.
- [ ] 3.2 `servers/search.py::search_indicators`: annotate `-> SearchResponse`, `return response` (drop `model_dump(exclude_none=True)`).

## 4. Tests

- [ ] 4.1 Update the non-e2e handler tests that assert dict keys → model attributes. **PRIMARY (the gate driver): `tests/test_output_handler.py`** — it has no e2e marker and asserts `result["output_mode"]`, `result["data"]["variable"][...]`, `result["file_path"]`, `result["format"]`, `result["multi_file"]`, `result["rows_written"]`, `result["file_size_bytes"]` ~20× → change to `result.output_mode`, `result.data.*`, `result.file_path`, `result.format`, etc. Also update `tests/test_integration.py`, and `tests/test_e2e.py` (the latter is `@pytest.mark.e2e` so skipped by the gate, but keep it correct).
- [ ] 4.2 Because `PaginationResult.to_dict()` is RETAINED (task 2.2), `tests/test_pagination_handler.py` and `tests/test_multi_file_exporter.py::test_to_dict` stay green unchanged — confirm they still pass (no rewrite needed).
- [ ] 4.3 Add a `Client(mcp)` test (in a new or the existing in-memory test module) asserting: both tools' `outputSchema` is field-level (NOT `{"type":"object","additionalProperties": true}`); a `search_indicators` call's `structured_content` matches `SearchResponse`; a `get_observations` call with `output="screen"` yields the screen model and a call with `output="file"` (forces `_handle_file_output` regardless of threshold) yields the file model.
- [ ] 4.4 Confirm `tests/test_services.py` search assertions (on the `SearchResponse` model at the service layer) still pass unchanged (the service already returns the model; only the tool boundary changed).

## 5. Verification

- [ ] 5.1 `uv run ruff format --check && uv run ruff check && uv run pytest -m "not e2e"` → all pass.
- [ ] 5.2 Server boots (`python datacommons_mcp/run_server.py`, EOF) with both tools registered; `Client(mcp).list_tools()` shows field-level output schemas for both.
- [ ] 5.3 `uv lock --check` consistent.
- [ ] 5.4 Commit per logical group (conventional commits), then Gate 2 (code review) before docs.
