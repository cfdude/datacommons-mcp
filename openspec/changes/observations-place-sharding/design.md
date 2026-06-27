## Context

Flow today: `tools/observations.py::get_observations` → `get_observations_paginated` (validates, runs the C guardrail via `count_child_places`, A-i facet-reduction, fetches, materializes ONE `ObservationToolResponse`) → `output_handler.handle_observations` (routes screen vs file by row count) → `_handle_file_output` → `pagination_handler.fetch_with_auto_streaming` → `CSVStreamer`. `CSVStreamer` (csv_streamer.py) is a context manager whose `write_response_page(response, page_number)` appends incrementally and is shard-ready as-is. `client.fetch_obs`/`fetch_obs_page` already branch `fetch_observations_by_entity_type` (child) vs `fetch(entity_dcids=...)` (explicit) — both accept `filter_facet_ids`. Investigation facts in [[observations-streaming-reality]].

## Decisions

**1. Route by child count; `DC_MAX_PLACES` becomes a shard trigger.** In the tool/service, for a `child_place_type` query: `n = count_child_places(...)`; `n > DC_MAX_PLACES` → `ResultTooLargeError` (absolute ceiling, default raised to admit all-US-tracts ≈ 97,659, e.g. 150000); `DC_SHARD_SIZE < n ≤ DC_MAX_PLACES` → **sharded export**; `n ≤ DC_SHARD_SIZE` → existing A-i single fetch (unchanged). New config `DC_SHARD_SIZE` (default ~15000 — margin under the ~45k Count_Person 502 wall, conservative for heavier variables).

**2. The sharded path is a SEPARATE driver that returns an `ObservationsFileResult` directly** — it does NOT go through `get_observations_paginated`'s materialize-everything return or the screen/file routing (sharded queries are always file). New `sharded_export(client, request, config, storage...) -> ObservationsFileResult` (in `services/` or `utils/output_handler.py`). The tool branches to it before the normal path.

**3. Facet from the FIRST shard, reused for all.** A full all-facets probe over ALL places would itself exceed the cap, so probe only the first shard at `date="latest"` (all facets) → `rank_primary_facet` (shared with A-i) → primary. Pass `filter_facet_ids=[primary]` to every shard. *Why first-shard is enough:* verified a national facet covers 100% of distant shards. **Coverage guard:** per shard, if the primary covers `< DC_SHARD_FACET_MIN_COVERAGE` (e.g. 0.8) of the shard's returned places, `log.warning` (regionally-sourced variables may fragment); `source_override` forces an explicit facet and skips the probe.

**4. Shard loop, write-and-release, per-shard metadata.** Enumerate `fetch_child_place_dcids(parent, child_type)` → `list[str]`; slice into `DC_SHARD_SIZE` chunks. Open `CSVStreamer` once; for each shard: build a request with `entity_dcids=shard` + `source_ids=[primary]`; `client.fetch_observations_by_entity_dcid(...)` (new method) → `_fetch_all_metadata` for the shard's places → `_build_final_response` → small `ObservationToolResponse` → `streamer.write_response_page(resp, page_number=i+1)` → drop the reference. Sum `rows_written`. **No empty-series / `alternative_sources` reconstruction** (A-i's carry-forward) — a file export emits zero rows for places without the primary source, so they're simply absent; `ObservationsFileResult` doesn't carry `alternative_sources` anyway.

**5. Adaptive retry on BOTH 500 and 502.** `fetch_shard(shard)`: try; on the API's size errors (HTTP 500 "concurrent ... series" OR 502 timeout — match both, since the dcid path hits 502 first), split the shard in half and recurse on each half; floor at `DC_SHARD_MIN` (e.g. 1000) — a floor shard that still fails raises a clear error. This absorbs the variable-dependent wall without hand-tuning `DC_SHARD_SIZE` per variable.

**6. `ObservationsFileResult`** unchanged shape + a `shards` count; `rows_written` summed; `preview`/`summary` from the first written shard; `pages_fetched` repurposed or set to shard count (decide in apply — keep it honest).

**7. Remove dead pagination code** (`_stream_to_file` `next_token` loop, `_write_api_response_page`) — confirmed inert on v2; do not build on it.

## Risks / Trade-offs

- **502 wall is variable-dependent, not a constant** → conservative `DC_SHARD_SIZE` + adaptive halving (Decision 5) is the real safety; `DC_SHARD_SIZE` is a starting point, not a guarantee.
- **Regional-variable facet coverage** (Q4 unverified for non-census vars) → coverage-guard warning + `source_override`. A future option: per-shard facet selection (rejected for v1 — inconsistent sources across one file).
- **New write path bypassing the existing flow** → mitigated by reusing the already-incremental `CSVStreamer` and the existing `_build_final_response`/`_fetch_all_metadata` per shard.
- **Wall-clock** for the largest exports is minutes (~5-7 shards × seconds), not memory-bound. `DC_MAX_PLACES` caps the absurd.
- **Multi-variable** sharding not investigated → single-variable scope; note as follow-up.

## Migration Plan (staged)

1. Client: `fetch_observations_by_entity_dcid(variable_dcid, entity_dcids: list[str], date, filter_facet_ids)` (clients/observations.py); `fetch_child_place_dcids(parent, child_type) -> list[str]` (clients/entities.py; `count_child_places` reuses it).
2. Config: `DC_SHARD_SIZE` (default 15000), `DC_SHARD_MIN` (1000), `DC_SHARD_FACET_MIN_COVERAGE` (0.8); raise `DC_MAX_PLACES` default to ~150000 (now a shard trigger / absolute ceiling).
3. Sharded driver: enumerate → first-shard facet probe → shard loop (adaptive `fetch_shard` with 500/502 halving) → per-shard build + `write_response_page` → `ObservationsFileResult`. Coverage guard.
4. Route in the tool/service by `count_child_places` vs `DC_SHARD_SIZE`/`DC_MAX_PLACES`.
5. Remove dead pagination code.
6. Tests + `docs/reference.md`.
7. Gate: ruff + mypy + full suite + coverage ≥ 80; a live manual sanity export of a beyond-cap geography (e.g. all tracts of one state, or a capped subset) if a key is available.

**Rollback:** revert; new path is additive (the ≤ `DC_SHARD_SIZE` path is unchanged), so reverting restores the refusal behavior for big queries.

**Open for Gate 1:** exact home of the driver (services vs output_handler); whether `pages_fetched` should become `shards`; whether per-shard metadata fetch is acceptable vs one upfront names fetch; the precise exception types/messages the lib raises for 500 vs 502 (apply must confirm against the real `datacommons_client` error classes).
