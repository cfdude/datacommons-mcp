## Why

When `get_observations` returns a large result, it streams to a CSV/JSON file and returns `ObservationsFileResult` with only path + counts (`file_path`, `rows_written`, `pages_fetched`, `file_size_bytes`, `unique_places_count`, `format`). The agent/user gets **no sense of the content** until they open the file on disk — they can't see what was returned, confirm it's the right data, or reason about it in the conversation.

The data is **already fully materialized** in memory when the file result is built (the DC client returns the whole dataset; see [[observations-streaming-reality]]), so a bounded sample + a few summary fields are essentially free — no extra retention, no second pass, no disk re-read.

## What Changes

`ObservationsFileResult` gains a bounded **preview** + **summary metadata**, populated in `OutputHandler._handle_file_output` from the already-in-scope `processed_response`:

- `preview: list[ObservationPreviewRow]` — the first N (default 10) flattened observation rows, the same shape as the CSV rows (place dcid/name/type, variable dcid/name, date, value, source_id). Bounded — never the full dataset.
- `columns: list[str]` — the CSV column headers, so the agent knows the schema without opening the file.
- `variable_name: str | None` — the variable's display name (caption for the agent).
- `summary: str` — a human/agent-readable message, e.g. `"12,345 rows written to <path> (csv). Showing the first 10 of 12,345 rows; open the file for the full dataset."` — covering the three user goals: a sample is shown, the total record count is stated, and the full file's location is given.

`rows_written` is already the **true total** (nothing is truncated today), so it is the authoritative record count the summary cites. A new `ObservationPreviewRow` model (mirroring the CSV row) is added so the preview carries a real field-level schema (consistent with the typed structured-output work in 4d).

**CLIENT-VISIBLE change (intended, additive):** the file-mode result gains `preview`/`columns`/`variable_name`/`summary`. The screen-mode result is unchanged. No data is inlined beyond the bounded preview; the full dataset still goes only to the file.

Non-goals: NO change to the streaming/pagination behavior or memory profile (that's the separate, measure-first #1 investigation — see [[observations-streaming-reality]]); NO `truncated`/`total_available` fields (inert until real streaming exists); NO async "sample now, file later" (the tool is synchronous — the file is already written when the result returns).

## Capabilities

### New Capabilities
- `observations-file-preview`: the `get_observations` file-mode result includes a bounded row preview, the column schema, the variable name, and a summary message stating the total rows written and the file location — so an agent can see and reason about large exports without opening the file.

## Impact

- **Code:** `data_models/observations.py` (new `ObservationPreviewRow`; add `preview`/`columns`/`variable_name`/`summary` to `ObservationsFileResult`); `utils/output_handler.py::_handle_file_output` (build the preview via `islice(flatten_response_to_rows(processed_response), N)` + the summary); a `N` constant.
- **Tests:** add file-result preview assertions in `test_output_handler.py` and the `Client(mcp)` `test_structured_output.py`; existing file-result asserts are unaffected (additive fields).
- **Risk:** LOW. Additive fields, bounded preview, data already in memory; behavior-preserving for everything else.
