## Why

`get_observations` cannot export geographies past the Data Commons v2 size limits at all: the API does not paginate and **rejects** big queries. Investigation ([[observations-streaming-reality]], live) found TWO walls — HTTP **500** ("concurrent observation series") on the all-facets `entity_type` path, and HTTP **502** gateway *timeout* (~25-30 s) on the filtered explicit-DCID path at large batches; the 502 wall is **variable-dependent** (Count_Person filtered: 45k places at `date="all"` OK, 48k fails). So today, all-US-census-tracts (97,659) and similar exports are impossible — and the C guardrail simply *refuses* them. The company needs these large exports.

This is item A-ii: export arbitrarily large child-place geographies by **sharding the place list into batches**, querying each batch with explicit `entity_dcids` + the primary facet, writing each batch's rows straight to the CSV, and releasing it — **O(shard) memory**, no single oversized request. Verified live: `entity_dcids` is a POST body (carried all 97,659 tracts, no URL limit; composes with `filter_facet_ids`); per-shard memory is flat (~226 MB for 20k tracts × all dates × 1 facet, released between shards); `CSVStreamer` already appends incrementally; and for a national variable a single primary facet covers 100% of every shard.

## What Changes

A new **sharded-export path** for big child-place file exports, composing with A-i (facet reduction) and reframing C (the guardrail):

- **Trigger by place count.** For a `child_place_type` query, the existing `count_child_places` decides the path: `count ≤ DC_SHARD_SIZE` → the current single facet-reduced fetch (A-i, unchanged); `DC_SHARD_SIZE < count ≤ DC_MAX_PLACES` → **shard**; `count > DC_MAX_PLACES` → refuse (an absolute wall-clock safety ceiling). **C's `DC_MAX_PLACES` flips from a hard refusal to a shard trigger**; its default is raised so all-US-tracts-scale exports are permitted.
- **Enumerate** the child DCIDs via `fetch_place_children` (new `fetch_child_place_dcids(parent, child_type) -> list[str]`; `count_child_places` reuses it). Slice into shards of `DC_SHARD_SIZE`.
- **Pick one global primary facet** from a cheap `date="latest"` probe over the FIRST shard (a representative sample — the full all-facets probe over all places would itself exceed the cap), via the shared `rank_primary_facet` (A-i). Reuse that facet for every shard through `filter_facet_ids`. **Coverage guard:** if the facet covers < a threshold of a later shard's places, log a warning (protects regionally-sourced variables, where one source may not blanket the country).
- **Shard loop, write-and-release.** Open `CSVStreamer` once; for each shard: `fetch_observations_by_entity_dcid(shard, filter_facet_ids=[primary], date)` (new client method) → process to a small `ObservationToolResponse` → `write_response_page` → release. Close at the end. Force file output (these are always large); bypass the materialize-everything `get_observations_paginated` return. NOTE: a file export needs **no** empty-series/`alternative_sources` reconstruction (A-i's complexity) — places without the primary source contribute zero CSV rows.
- **Adaptive shard retry.** On HTTP 500 OR 502 for a shard, halve it and retry (down to a floor, e.g. 1000); if the floor still fails, error clearly. Handles the variable-dependent timeout wall without a hand-tuned size.
- **`ObservationsFileResult`** is returned as today — `rows_written` summed across shards, `preview`/`summary` from the first shard, plus `shards` count.
- **Cleanup:** remove the dead `_stream_to_file` `next_token` loop and `_write_api_response_page` (the v2 API never paginates — confirmed; building on them is building on nothing).

**CLIENT-VISIBLE changes (intended):** child-place exports that C used to refuse (e.g. all US census tracts) now **succeed**, written shard-by-shard to one CSV in bounded memory (minutes of wall-clock for the largest). Output for non-sharded (≤ `DC_SHARD_SIZE`) queries is unchanged.

Non-goals: NO change to single-place / screen-mode / `≤ DC_SHARD_SIZE` queries; NO multi-variable sharding tuning (investigated single-variable only — note as a follow-up); NO attempt to export truly pathological geographies (block-group/block scale) — bounded by `DC_MAX_PLACES`.

## Capabilities

### New Capabilities
- `observations-place-sharding`: `get_observations` exports child-place geographies larger than a single API request can handle by sharding the place list, querying explicit DCID batches with the primary facet, and streaming each batch to one CSV in O(shard) memory — with adaptive retry against the API's (variable-dependent) size walls and a coverage guard on the shared facet.

## Impact

- **Code:** `clients/observations.py` (`fetch_observations_by_entity_dcid` shard method) + `clients/entities.py` (`fetch_child_place_dcids`); a new sharded-export driver (e.g. `services/sharding.py` or `utils/output_handler.py`) owning enumerate → probe facet → loop → write; `services/observations.py` / `tools/observations.py` (route to sharding by count); `config.py` (`DC_SHARD_SIZE`; raise/repurpose `DC_MAX_PLACES`); remove dead pagination code in `pagination_handler.py`.
- **Tests:** shard slicing + count routing; the shard loop writes each batch and accumulates `rows_written` (mock the client to return per-shard responses); adaptive halving on a simulated 500/502; coverage-guard warning; facet reused across shards; `DC_SHARD_SIZE`/`DC_MAX_PLACES` thresholds; force-file; existing A-i/C tests unaffected.
- **Docs:** `docs/reference.md` — large exports now shard (no longer refused), `DC_SHARD_SIZE`/`DC_MAX_PLACES`, the wall-clock expectation, the regional-variable coverage caveat.
- **Risk:** HIGH (largest change in this arc). The 502 wall is variable-dependent (mitigated by conservative `DC_SHARD_SIZE` + adaptive retry on BOTH 500/502); regional-variable facet coverage (mitigated by the coverage guard + `source_override`); a new file-write path that bypasses the existing flow (mitigated by reusing the incremental `CSVStreamer`). Could not verify: the exact hard-500 series number, regional-variable coverage, multi-variable behavior.
