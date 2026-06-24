## 1. Models

- [x] 1.1 In `data_models/observations.py`, add `ObservationPreviewRow(ToolResponseBaseModel)` mirroring `CSVRow`: `place_dcid: str`, `place_name: str | None`, `place_type: str | None`, `variable_dcid: str`, `variable_name: str | None`, `date: str`, `value: float`, `source_id: str | None = None`.
- [x] 1.2 Add to `ObservationsFileResult`: `variable_name: str | None = None`, `columns: list[str] = Field(default_factory=list)`, `preview: list[ObservationPreviewRow] = Field(default_factory=list)`, `summary: str = ""`. (Keep them defaulted so existing construction sites/tests don't break.)

## 2. Populate the preview in the handler

- [x] 2.1 In `utils/output_handler.py::_handle_file_output`, after the `PaginationResult` is produced, build the preview from the already-in-scope `processed_response`:
  - `preview_rows = [ObservationPreviewRow(**asdict(r)) for r in islice(flatten_response_to_rows(processed_response), _PREVIEW_ROWS)]` (import `islice`, `asdict`, `flatten_response_to_rows`, `CSVStreamer`).
  - `columns = list(CSVStreamer.HEADERS)`.
  - `variable_name = processed_response.variable.name`.
  - `summary = f"{result.rows_written} rows written to {file_path} ({output_format}). Showing the first {len(preview_rows)} of {result.rows_written} row(s); open the file for the full dataset."` (use the actual `file_path` and `rows_written`).
  - Pass all four into the `ObservationsFileResult(...)`.
- [x] 2.2 Add a module constant `_PREVIEW_ROWS = 10`.

## 3. Tests

- [x] 3.1 `tests/test_output_handler.py`: in a file-mode test (e.g. `test_file_mode_returns_statistics` or a new test), assert `result.preview` is non-empty for a multi-row response, `len(result.preview) <= _PREVIEW_ROWS`, `result.columns == list(CSVStreamer.HEADERS)`, `result.variable_name` is set, and `result.summary` contains the **`file_path` and `rows_written` as substrings** (assert substrings, NOT the exact parenthetical wording, so a later message tweak doesn't break the test). Add a case where total rows ≤ N → `len(result.preview) == total`.
- [x] 3.2 `tests/test_structured_output.py`: in the `output="file"` Client(mcp) path (or a new test), assert the file result's `structured_content` carries `preview`, `summary`, and `columns`. The fake `get_observations_service` MUST return a response with populated `place_observations` (so the preview is non-empty), and the test MUST point storage at a temp dir (`monkeypatch.setenv("DC_STORAGE_DIR", str(tmp_path))`) so it does NOT write a real CSV into `~/Documents/datacommons-data`.
- [x] 3.3 Confirm existing file-result assertions (`test_output_handler.py`, `test_pagination_handler.py`, `test_multi_file_exporter.py`) still pass (additive fields).

## 4. Verification

- [x] 4.1 `uv run --extra dev ruff format --check && uv run --extra dev ruff check && uv run --extra dev mypy src/datacommons_mcp && uv run --extra dev pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` → all pass.
- [x] 4.2 Manual sanity (if a DC_API_KEY is available): a forced `output="file"` query returns a result whose `summary` reads sensibly and `preview` shows real rows.
- [x] 4.3 Commit per logical group; Gate 2 (code review) before docs/archive.
