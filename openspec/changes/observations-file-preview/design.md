## Context

`get_observations` file-mode returns `ObservationsFileResult` (path + counts) built in `OutputHandler._handle_file_output` (`utils/output_handler.py`), which already has the full `processed_response: ObservationToolResponse` in scope. `utils/csv_streamer.py` provides `flatten_response_to_rows(response) -> Iterator[CSVRow]` (the exact rows written to the CSV) and `CSVStreamer.HEADERS` (the 8 columns). The dataset is fully materialized in memory at this point ([[observations-streaming-reality]]), so a sample is free.

## Decisions

**1. Take the preview from `flatten_response_to_rows` + `islice`, in `_handle_file_output`.** Reuse the exact CSV-row generator so the preview matches the file's rows precisely; `itertools.islice(gen, N)` bounds it with no extra retention or second pass. *Alternative (tap the CSV writer / re-read the file):* rejected — needs a write-path hook or disk round-trip.

**2. Typed `ObservationPreviewRow` (pydantic), not `list[dict]`.** A typed row gives a real field-level output schema (consistent with the 4d structured-output work) instead of an open object. Mirror `CSVRow`'s fields exactly (`place_dcid`, `place_name`, `place_type`, `variable_dcid`, `variable_name`, `date`, `value`, `source_id`). Map `CSVRow → ObservationPreviewRow` when building the preview.

**3. `summary` is composed by the tool, not the agent.** A single string field directly serves the user's "include a message" ask and gives the agent a ready caption: `f"{rows_written} rows written to {file_path} ({format}). Showing the first {len(preview)} of {rows_written} row(s); open the file for the full dataset."` Cite `rows_written` (the true total).

**4. N = 10, a module constant.** Small enough to keep the response light, large enough to be representative. Not configurable (no demonstrated need).

**5. No `truncated`/`total_available`.** `rows_written` is the true total today; those fields would be inert until real streaming exists and would mislead. Out of scope.

## Risks / Trade-offs

- **Preview adds rows to the response** → bounded to N=10 typed rows; trivial vs. the file. The whole point of file-mode (not inlining the dataset) is preserved.
- **`preview` for a JSON-format file** → `flatten_response_to_rows` is format-independent (it flattens the response, not the file), so the preview is identical regardless of `format`. Fine.
- **Empty result forced to file** → `preview = []`, `summary` says "0 rows" — handled.
- **The preview is page-1-only — sound ONLY while streaming is inert.** Today the DC client returns the whole dataset on "page 1" ([[observations-streaming-reality]]), so `processed_response` IS the full dataset and the preview represents it faithfully. If a future real-streaming change (#1) ever makes the multi-page loop actually run, later pages would NOT be in `processed_response`, so the preview source must be revisited then. The `summary` ("first K of `rows_written`") stays arithmetically honest regardless, but #1 must re-examine where the preview rows come from.

## Migration Plan

1. `data_models/observations.py`: add `ObservationPreviewRow`; add `preview: list[ObservationPreviewRow] = []`, `columns: list[str] = []`, `variable_name: str | None = None`, `summary: str = ""` to `ObservationsFileResult`.
2. `utils/output_handler.py`: in `_handle_file_output`, build `preview` (islice N over `flatten_response_to_rows(processed_response)` → `ObservationPreviewRow`), `columns = list(CSVStreamer.HEADERS)`, `variable_name`, and `summary`; pass them into `ObservationsFileResult`. Add `N` constant.
3. Tests: `test_output_handler.py` (assert the new fields on a file result, incl. preview length bounding); `test_structured_output.py` (`Client(mcp)`: the file result's structured content carries `preview`/`summary`/`columns`).
4. Gate: ruff + mypy + full suite + coverage ≥ 80.

**Rollback:** revert; additive model/handler change, no data migration.
