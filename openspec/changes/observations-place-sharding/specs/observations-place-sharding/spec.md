## ADDED Requirements

### Requirement: Large child-place exports are sharded, not refused
When a `child_place_type` query spans more places than a single API request can handle, `get_observations` SHALL export it by sharding the place list rather than refusing it.

#### Scenario: A query above the shard size shards
- **WHEN** a `child_place_type` query's child-place count exceeds `DC_SHARD_SIZE` (and is within `DC_MAX_PLACES`)
- **THEN** the export is produced by querying the places in batches of at most `DC_SHARD_SIZE` (explicit `entity_dcids`), writing each batch's rows to a single CSV, and the result is an `ObservationsFileResult`

#### Scenario: A query within the shard size is unchanged
- **WHEN** the child-place count is at or below `DC_SHARD_SIZE`
- **THEN** the existing single facet-reduced fetch (item A-i) is used, unchanged

#### Scenario: An over-ceiling query is still refused
- **WHEN** the child-place count exceeds `DC_MAX_PLACES`
- **THEN** the query is refused with `ResultTooLargeError` (an absolute wall-clock safety ceiling) — `DC_MAX_PLACES` is now a shard trigger up to this ceiling, not a blanket refusal

### Requirement: Sharded export uses bounded memory
The sharded path SHALL hold at most one shard's data at a time.

#### Scenario: One shard in flight
- **WHEN** the shard loop runs
- **THEN** each shard's response is processed, written to the open CSV, and released before the next shard is fetched (peak memory is O(shard), not O(total geography))

#### Scenario: The CSV is one file, written incrementally
- **WHEN** multiple shards are written
- **THEN** they go to a single CSV via one open `CSVStreamer` (opened once, each shard appended, closed at the end), and `rows_written` is the sum across shards

### Requirement: One primary facet is chosen and reused across shards
The sharded path SHALL pick a single primary facet from a sample and apply it to every shard, guarding coverage.

#### Scenario: Facet picked from a sample probe, reused
- **WHEN** the export begins
- **THEN** a `date="latest"` probe over the first shard ranks facets (shared `rank_primary_facet`) to pick the primary, which is passed as `filter_facet_ids` for every shard's fetch

#### Scenario: Coverage guard warns on regionally-sparse facets
- **WHEN** the chosen facet covers fewer than a threshold fraction of a later shard's places
- **THEN** a warning is logged (the single global facet may miss regionally-sourced data); an explicit `source_override` bypasses auto-selection

### Requirement: Sharding adapts to the API's size walls
Because the API rejects oversized requests two ways (HTTP 500 series cap; HTTP 502 timeout) and the limit is variable-dependent, the shard loop SHALL adapt.

#### Scenario: A failed shard is halved and retried
- **WHEN** a shard fetch fails with HTTP 500 or HTTP 502
- **THEN** the shard is split in half and each half retried (recursively, down to a floor size); if a shard at the floor still fails, the export errors with a clear message

### Requirement: Enumeration yields the full child DCID list
Sharding SHALL slice the complete list of child place DCIDs.

#### Scenario: Child DCIDs enumerated
- **WHEN** sharding starts
- **THEN** `fetch_child_place_dcids(parent, child_place_type)` returns the full DCID list (via `fetch_place_children`), and `count_child_places` is consistent with it

### Requirement: Dead pagination code is removed
The non-functional v2 pagination scaffolding SHALL be removed as part of this change.

#### Scenario: next_token scaffolding gone
- **WHEN** the change lands
- **THEN** the dead `_stream_to_file` `next_token` loop and `_write_api_response_page` (the v2 API never returns a next_token) are removed, and the suite stays green

### Requirement: Suite and docs stay green
The change SHALL keep the suite green and document the new behavior.

#### Scenario: Tests pin the sharded contract
- **WHEN** the suite runs
- **THEN** tests cover count-based routing, shard slicing, write-and-accumulate, adaptive halving on 500/502, the coverage-guard warning, facet reuse, the thresholds, and force-file — and the full non-e2e suite passes
