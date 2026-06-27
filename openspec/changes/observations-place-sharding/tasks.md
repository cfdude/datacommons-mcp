## 1. Client methods

- [ ] 1.1 `clients/observations.py`: add `fetch_observations_by_entity_dcid(variable_dcid: str, entity_dcids: list[str], date, filter_facet_ids: list[str] | None) -> ObservationApiResponse` wrapping `self.dc.observation.fetch_observations_by_entity_dcid(...)` (POST body; verified to carry tens of thousands of DCIDs + compose with `filter_facet_ids`).
- [ ] 1.2 `clients/entities.py`: add `fetch_child_place_dcids(parent_place_dcid, child_place_type) -> list[str]` (from `fetch_place_children(..., as_dict=True)` → `[d["dcid"] for d in resp.get(parent, [])]`). Refactor `count_child_places` to `len(fetch_child_place_dcids(...))` (or share the underlying call) so count and list cannot drift.

## 2. Config

- [ ] 2.1 `config.py`: add `shard_size` (alias `DC_SHARD_SIZE`, default 15000, ge≥1), `shard_min` (alias `DC_SHARD_MIN`, default 1000), `shard_facet_min_coverage` (alias `DC_SHARD_FACET_MIN_COVERAGE`, default 0.8, 0–1). Raise `max_places` default to ~150000 and update its description: now a SHARD TRIGGER up to an absolute ceiling, not a blanket refusal.

## 3. Sharded export driver

- [ ] 3.1 New `sharded_export(client, request, output_config, ...) -> ObservationsFileResult` (home TBD in Gate 1 — `services/` vs `utils/output_handler.py`). Steps below.
- [ ] 3.2 Enumerate: `dcids = await client.fetch_child_place_dcids(request.place_dcid, request.child_place_type)`; `shards = [dcids[i:i+shard_size] for ...]`.
- [ ] 3.3 Facet: if `request.source_ids` set, use it; else probe the FIRST shard at `date="latest"` (`fetch_observations_by_entity_dcid(shard0, filter_facet_ids=None, date=latest)`) → `rank_primary_facet` → `primary`. If no facet, fall back gracefully.
- [ ] 3.4 Adaptive `fetch_shard(shard) -> ObservationApiResponse`: try `fetch_observations_by_entity_dcid(shard, filter_facet_ids=[primary], date=request.date_type)`; on the lib's HTTP-500 ("concurrent ... series") OR HTTP-502 error (confirm the real exception classes from `datacommons_client`), if `len(shard) > shard_min` split in half and recurse+concat; else re-raise with a clear message.
- [ ] 3.5 Loop: open one `CSVStreamer`; for each shard `i`: `api_resp = await fetch_shard(shard)`; coverage guard — if the primary covers `< shard_facet_min_coverage` of the shard's returned places, `logger.warning(...)`; `metadata = await _fetch_all_metadata(client, var, api_resp, request.place_dcid)`; `resp = await _build_final_response(request_with_source_ids_primary, api_resp, metadata)`; `streamer.write_response_page(resp, page_number=i+1)`; accumulate `rows_written`; drop references. Close streamer.
- [ ] 3.6 Return `ObservationsFileResult(file_path, rows_written=total, shards=len(shards), format, preview=<first shard rows>, summary=...)`. Decide `pages_fetched` (→ shard count) honestly.

## 4. Routing

- [ ] 4.1 In the tool/service path for a `child_place_type` query: `n = count_child_places(...)`; `n > max_places` → `ResultTooLargeError` (absolute ceiling); `n > shard_size` → `sharded_export(...)` (force file, return its `ObservationsFileResult`); else the existing A-i path. Keep single-place / explicit-`source_override`-non-child / screen paths unchanged.

## 5. Cleanup

- [ ] 5.1 Remove the dead `_stream_to_file` `next_token` loop and `_write_api_response_page` from `pagination_handler.py` (v2 never paginates). Keep the parts still used by the ≤shard-size file path; ensure that path still works.

## 6. Tests

- [ ] 6.1 `fetch_child_place_dcids` returns the DCID list; `count_child_places` consistent (mock `fetch_place_children`).
- [ ] 6.2 Routing: `count ≤ shard_size` → A-i path (no sharding); `shard_size < count ≤ max_places` → sharded_export called; `count > max_places` → `ResultTooLargeError`.
- [ ] 6.3 Shard loop: mock the client so a 3-shard export writes all 3 (assert `write_response_page` called 3×, `rows_written` summed, one `CSVStreamer` opened/closed).
- [ ] 6.4 Adaptive halving: a `fetch_shard` that raises the size error for a big shard but succeeds for halves → assert it splits and completes; a floor-size shard that still fails → clear error.
- [ ] 6.5 Facet: probe runs on shard 0 only; the same `filter_facet_ids=[primary]` is passed to every shard fetch. Coverage guard logs a warning when a shard's coverage is below the threshold.
- [ ] 6.6 `DC_SHARD_SIZE`/`DC_MAX_PLACES` defaults; existing A-i + C tests still pass.

## 7. Docs + verification

- [ ] 7.1 `docs/reference.md`: large child-place exports now SHARD (no longer refused); `DC_SHARD_SIZE` / raised `DC_MAX_PLACES`; wall-clock expectation; the regional-variable coverage caveat + `source_override`.
- [ ] 7.2 `uv run --extra dev ruff format --check && ruff check && mypy src/datacommons_mcp && pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` → all pass.
- [ ] 7.3 (If DC_API_KEY available) live manual sanity: export a beyond-single-request geography (e.g. all census tracts of a large state, or all US tracts) — completes, bounded memory, correct row count, one CSV. Commit per group; Gate 2 before docs/archive.
