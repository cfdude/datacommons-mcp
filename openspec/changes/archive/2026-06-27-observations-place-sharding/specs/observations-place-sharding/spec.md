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

#### Scenario: The ceiling can actually admit all-US-tracts
- **WHEN** `DC_MAX_PLACES` default and field bound are set
- **THEN** the default is 150000 and the field `le` bound is raised to accommodate it (the prior `le=100000` made a 150000 ceiling unsettable and left all-US-tracts ≈ 97,659 at the edge)

#### Scenario: Shard config is coherent
- **WHEN** `DC_SHARD_MIN`, `DC_SHARD_SIZE`, `DC_MAX_PLACES` are loaded
- **THEN** a validator enforces `shard_min ≤ shard_size ≤ max_places`

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

#### Scenario: Facet picked from a spread sample, reused
- **WHEN** the export begins
- **THEN** a `date="latest"` probe over a sample SPREAD across the geography (not the first contiguous, geoId-clustered shard) ranks facets (shared `rank_primary_facet`) to pick the primary, which is passed as `filter_facet_ids` for every shard's fetch

#### Scenario: Coverage guard measures against the requested shard and surfaces the shortfall
- **WHEN** the chosen facet returns data for fewer than `DC_SHARD_FACET_MIN_COVERAGE` of the places in a REQUESTED shard (denominator = `len(shard)`, NOT the returned places — filtering to the primary makes returned-coverage ~100% always)
- **THEN** the shortfall is accumulated and **surfaced in the `ObservationsFileResult`** (`places_missing` + a note in `summary`) so the calling agent can see it — not only logged; an explicit `source_override` bypasses auto-selection

### Requirement: Sharding adapts to the API's size walls
Because the API rejects oversized requests two ways (HTTP 500 series cap; HTTP 502 timeout) and the limit is variable-dependent, the shard loop SHALL adapt.

#### Scenario: A failed shard is halved and each leaf written
- **WHEN** a shard fetch fails with a `DCStatusError` whose `status_code` is 500 or 502
- **THEN** the shard is split in half and each half retried (recursively, down to `DC_SHARD_MIN`), and each successful LEAF sub-shard is written as its own page (nothing is concatenated); if a shard at the floor still fails, the export errors with a clear message naming the variable and size (a generic 500 is not distinguishable by reason, so the floor is the safety)

### Requirement: Enumeration yields the full child DCID list
Sharding SHALL slice the complete list of child place DCIDs.

#### Scenario: Child DCIDs enumerated
- **WHEN** sharding starts
- **THEN** `fetch_child_place_dcids(parent, child_place_type)` returns the full DCID list (via `fetch_place_children`), and `count_child_places` is consistent with it

### Requirement: Dead pagination code is removed
The non-functional v2 pagination scaffolding SHALL be removed as part of this change.

#### Scenario: next_token scaffolding gone, single-page path intact
- **WHEN** the change lands
- **THEN** only the unreachable `while next_token` loop and `_write_api_response_page` are removed (the v2 API never returns a next_token); `_stream_to_file` itself — the LIVE single-page file path — is kept, and a test proves a ≤ `DC_SHARD_SIZE` file export still writes correctly

### Requirement: Suite and docs stay green
The change SHALL keep the suite green and document the new behavior.

#### Scenario: Tests pin the sharded contract
- **WHEN** the suite runs
- **THEN** tests cover count-based routing, shard slicing, write-and-accumulate, adaptive halving on 500/502, the coverage-guard warning, facet reuse, the thresholds, and force-file — and the full non-e2e suite passes
