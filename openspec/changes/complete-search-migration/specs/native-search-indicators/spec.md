## ADDED Requirements

### Requirement: Search is served from the real search-indicators implementation
The `search_indicators` tool SHALL obtain results from `DCClient.search_indicators()` (the native `/api/nl/search-indicators` flow), not from the legacy search-vector path or the temporary shim.

#### Scenario: The service routes to the native client method
- **WHEN** `services/search.py::search_indicators` runs
- **THEN** it calls `client.search_indicators(...)` and does NOT call `fetch_indicators` / a legacy `_search_vector` / `_call_search_indicators_temp`

#### Scenario: The legacy/shim chain and flag are removed
- **WHEN** the source tree is inspected
- **THEN** `search_svs`, `_call_search_indicators_temp`, `_transform_search_indicators_to_svs_format`, `fetch_indicators`, the client `_search_vector`, `_filter_variables_by_existence`, `_filter_topics_by_existence`, `_get_topics_members_with_existence`, `_build_lookups`, the service `_search_vector`/`_merge_search_results`, and the `use_search_indicators_endpoint` config field/param are all absent

### Requirement: The full tool response contract is preserved
Migrating to the native flow SHALL NOT drop any field of the tool's `SearchResponse`. Because `client.search_indicators` returns only names/topics/variables, the service SHALL still resolve place metadata to rebuild the remaining fields.

#### Scenario: Place type-mappings and resolved parent are preserved
- **WHEN** `search_indicators` is invoked with places and/or a `parent_place`
- **THEN** the returned `SearchResponse` still includes `dcid_place_type_mappings` and `resolved_parent_place` (the service calls `client.fetch_entity_infos` for the place DCIDs to build them), alongside `topics`, `variables`, and `dcid_name_mappings`

#### Scenario: Results preserve score-descending order within a search
- **WHEN** the native flow transforms a single search's API results (the live endpoint returns results score-descending)
- **THEN** that search's results are ordered by score descending (the transform sorts the raw API result dicts by `score` before building models), matching the prior shim's behavior

#### Scenario: Cross-search ordering follows the endpoint's response
- **WHEN** results from multiple search tasks are merged into the final response (deduplicated, first occurrence wins)
- **THEN** the cross-search order follows the order the search-indicators endpoint returns its query results in (the endpoint is authoritative for ranking). The legacy shim's place-specific-task-first ordering is intentionally NOT preserved — data is unaffected (each indicator carries its own `places_with_data`); only cross-task presentation order changes

### Requirement: Topic results are no longer silently dropped
The native flow SHALL surface topics identified by `typeOf == "Topic"` and topics that are not present in the local topic cache (both were dropped by the shim).

#### Scenario: A typeOf-identified topic not in the local cache is returned
- **WHEN** the endpoint returns an indicator with `typeOf == "Topic"` whose DCID is absent from the local topic store
- **THEN** it appears in the `SearchResponse.topics` (it is not dropped)

### Requirement: Place-like existence filtering is preserved
Routing to the native flow SHALL keep place-like (`PLACE_LIKE_CONSTRAINTS`) existence filtering working, including for recursive member-topic existence checks.

#### Scenario: Member-topic existence unions place-like data
- **WHEN** `_check_topic_exists_recursive` evaluates whether a member topic has data for a place
- **THEN** it unions `_place_like_statvar_store` with `variable_cache` (the same data the shared variable/topic existence helpers use), so place-like-only entities are counted

#### Scenario: place_like scaffolding is retained
- **WHEN** the source tree is inspected
- **THEN** `_constrained_vars.py`, `_compute_place_like_statvar_store`, and `_place_like_statvar_store` remain (their removal is gated on an upstream server endpoint, out of scope here)

### Requirement: Behavior is validated and the suite stays green
The migration SHALL be validated against the native flow's existing test coverage and a response-contract test, with no net loss of meaningful coverage.

#### Scenario: Native-flow tests become the live spec and pass
- **WHEN** the test suite runs after the migration
- **THEN** the existing `TestDCClientFetchIndicatorsNew` tests (which exercised the previously-dead native flow) pass against the now-live path, and the legacy/flag/shim tests are removed; the place-like guard test is re-pointed off the deleted `_filter_variables_by_existence` and still passes

#### Scenario: Suite and server stay green
- **WHEN** the full non-e2e suite runs and the stdio server boots after the migration
- **THEN** all non-e2e tests pass and the server starts and registers both tools without error
