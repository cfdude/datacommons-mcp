## 1. Client methods

- [x] 1.1 `clients/observations.py`: `fetch_observations_by_entity_dcid(variable_dcid: str, entity_dcids: list[str], date, filter_facet_ids: list[str] | None) -> ObservationApiResponse` wrapping `self.dc.observation.fetch_observations_by_entity_dcid(...)` (POST body; carries tens of thousands of DCIDs + composes with `filter_facet_ids` — verified).
- [x] 1.2 `clients/entities.py`: `fetch_child_place_dcids(parent_place_dcid, child_place_type) -> list[str]` (`fetch_place_children(..., as_dict=True)` → `[d["dcid"] for d in resp.get(parent, [])]`). Refactor `count_child_places` to reuse it so count and list can't drift.

## 2. Config (Gate-1 C1 / M4)

- [x] 2.1 `config.py`: add `shard_size` (`DC_SHARD_SIZE`, default 15000), `shard_min` (`DC_SHARD_MIN`, default 1000), `shard_facet_min_coverage` (`DC_SHARD_FACET_MIN_COVERAGE`, default 0.8, 0–1).
- [x] 2.2 `config.py`: `max_places` default 5000 → **150000** AND raise the field bound `le=100000 → 1000000` (C1: a 150000 default/ceiling is impossible under `le=100000`; all-US-tracts ≈ 97,659 must sit comfortably inside). Update the description: now a SHARD TRIGGER up to an absolute ceiling.
- [x] 2.3 Add a `model_validator` enforcing `shard_min ≤ shard_size ≤ max_places` (M4).

## 3. Generalize the file path to a page-producer (Gate-1 I1) — reuse, don't fork

- [x] 3.1 `utils/output_handler.py` / `pagination_handler.py`: generalize `_handle_file_output` (or `fetch_with_auto_streaming`) to consume an **async iterator of `ObservationToolResponse` pages**: open `CSVStreamer` once, `write_response_page` per page, build the `ObservationsFileResult` ONCE (preview from the first page). The normal path yields ONE page (today's behavior — must be unchanged); the sharded path yields N. Extract `_finalize_file_result(...)` if cleaner. CONFIRM every existing result field is preserved (preview/summary/columns/format/multi_file/companion_files/file_size_bytes/unique_places_count).
- [x] 3.2 `data_models/observations.py`: add `places_missing: int = 0` to `ObservationsFileResult` (I3 — coverage shortfall, agent-visible).
- [x] 3.3 Remove ONLY the dead `while next_token` loop (pagination_handler.py ~217-231) + `_write_api_response_page` (M1). KEEP `_stream_to_file` (it's the live single-page path). A test must prove a single-page (≤shard) file export still writes.

## 4. Sharded page-producer

- [x] 4.1 Enumerate via `fetch_child_place_dcids`; `shards = [dcids[i:i+shard_size] ...]`.
- [x] 4.2 Facet: if `request.source_ids` set, use it; else probe a SPREAD sample (`dcids[::stride][:shard_size]`, not the first contiguous shard — geoId clustering, I3) at `date="latest"` (`fetch_observations_by_entity_dcid(sample, filter_facet_ids=None, date=latest)`) → `rank_primary_facet` → primary. No facet → graceful fallback.
- [x] 4.3 Adaptive `fetch_shard(shard)` yields processed pages: try `fetch_observations_by_entity_dcid(shard, [primary], request.date_type)`; on `DCStatusError` with `status_code in (500, 502)`, if `len(shard) > shard_min` split in half and recurse, **writing each LEAF as its own page (no concat)**; else re-raise a clear error naming variable+size. **Verify a 502 arrives as `DCStatusError`, not a raw `requests.Timeout` that escapes the lib catch (I4) — widen the catch if so.**
- [x] 4.4 Per shard: `_fetch_all_metadata(client, var, api_resp, request.place_dcid)`; `_build_final_response(request-with-source_ids=[primary], api_resp, metadata)` → small `ObservationToolResponse` → yield. Drop references (no accumulation across shards).
- [x] 4.5 Coverage guard: per shard, `covered = places with primary data returned`; if `covered / len(shard) < shard_facet_min_coverage`, accumulate `len(shard) - covered` into `places_missing`. Set it on the result + mention in `summary`. (Denominator is the REQUESTED shard — C2.)
- [x] 4.6 `multi_file` is NOT supported on sharded exports (M6) — ignore/assert off.

## 5. Routing — one service orchestrator (Gate-1 I2)

- [x] 5.1 A single service entry for a `child_place_type` query enumerates ONCE (`fetch_child_place_dcids`, `n = len`) and dispatches: `n > max_places` → `ResultTooLargeError`; `n > shard_size` → sharded page-producer (force file); else → existing A-i single fetch. Thread the count/DCID list down — do NOT count in the tool then re-enumerate in the driver. `get_observations_paginated` keeps its own guardrail for direct/test callers. `pages_fetched` = number of shard fetches (M7), pinned by a test.

## 6. Tests

- [x] 6.1 `fetch_child_place_dcids` returns the DCID list; `count_child_places` consistent (mock `fetch_place_children`).
- [x] 6.2 Routing: `n ≤ shard_size` → A-i (no sharding); `shard_size < n ≤ max_places` → sharded; `n > max_places` → `ResultTooLargeError`. Enumerated once (assert `fetch_place_children`/`fetch_child_place_dcids` called once).
- [x] 6.3 Shard loop: a 3-shard export writes all 3 (assert `write_response_page` 3×, one `CSVStreamer`, `rows_written` summed, `pages_fetched==3`).
- [x] 6.4 Adaptive halving: `fetch_shard` raises a `DCStatusError(status_code=502)` for a big shard but succeeds for halves → splits, writes each leaf; a floor-size shard that still fails → clear error.
- [x] 6.5 Facet: probe runs on the spread SAMPLE only; same `filter_facet_ids=[primary]` to every shard. Coverage guard: a shard where the primary returns < threshold of `len(shard)` → `places_missing` incremented + surfaced in the result (denominator = requested shard, C2).
- [x] 6.6 Single-page file path still writes after the dead-code removal (M1).
- [x] 6.7 Config: `DC_SHARD_SIZE`/`DC_SHARD_MIN`/coverage defaults; `DC_MAX_PLACES` default **150000** and settable to it (C1); the `shard_min ≤ shard_size ≤ max_places` validator. **Update `test_max_places_default_is_5000` → 150000 (M2).**
- [x] 6.8 Existing A-i + C guardrail tests still pass (they pass `max_places` explicitly).

## 7. Docs + verification

- [x] 7.1 `docs/reference.md`: large child-place exports now SHARD (no longer refused); `DC_SHARD_SIZE` / raised `DC_MAX_PLACES`; wall-clock expectation; `places_missing` + the regional-variable coverage caveat + `source_override`.
- [x] 7.2 `uv run --extra dev ruff format --check && ruff check && mypy src/datacommons_mcp && pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` → all pass.
- [x] 7.3 (If DC_API_KEY available) live manual sanity: export a beyond-single-request geography (all tracts of a large state, or all US tracts) — completes, bounded memory (~one shard), correct row count, one CSV. Commit per group; Gate 2 before docs/archive.
