## Why

The `search_indicators` tool's live path is a **temporary shim**, not the real new-endpoint implementation. The default (`use_search_indicators_endpoint=True`) routes through `fetch_indicators` → client `_search_vector` → `_call_search_indicators_temp`, which hits the new `/api/nl/search-indicators` URL but **degrades the response back to the legacy flat SV/CosineScore format** (`_transform_search_indicators_to_svs_format`). The real implementation — `DCClient.search_indicators()` / `_fetch_indicators_new()` — already exists, is more faithful to the endpoint, but is **dead in production** (exercised only by tests). The shim's degradation has real consequences: topics are identified by DCID-prefix only (losing `typeOf`-identified topics) and **topics absent from the local topic cache are silently dropped**.

This is slice 4c of the decomposed `modularize-core` (#4) — the keystone, highest-risk slice. It is scoped to the **search migration only**; the `clients.py` (1224 LOC) module split is a separate mechanical follow-up (bundling a high-risk behavior change with a big mechanical split is what we decomposed #4 to avoid).

## What Changes

- **Route the search service to the real flow.** `services/search.py::search_indicators` calls `client.search_indicators(search_tasks, per_search_limit, include_topics)` instead of the legacy `_search_vector`/`fetch_indicators` chain.
- **Preserve the full tool contract at the service layer.** `client.search_indicators` returns only `status`/`dcid_name_mappings`/`topics`/`variables`. The service MUST still call `client.fetch_entity_infos` for the **place** DCIDs to rebuild `dcid_place_type_mappings` (contractual — `get_observations`'s docs instruct agents to use it) and `resolved_parent_place`. Missing this would be a client-visible regression.
- **Preserve result ordering.** Verified the live endpoint returns results in score-descending order; the real flow preserves API order, but to guarantee parity with the shim's explicit score-sort, the real transform SHALL order results by score descending.
- **Close the place_like member-topic gap.** `_check_topic_exists_recursive` (used by the real flow's member-topic existence check) currently reads only `variable_cache`; the legacy path unioned `_place_like_statvar_store`. Fix it to union place-like data so the migration does not silently degrade place-like existence filtering.
- **Delete the legacy/shim chain:** client `search_svs`, `_call_search_indicators_temp`, `_transform_search_indicators_to_svs_format`, `fetch_indicators`, client `_search_vector`, `_filter_topics_by_existence`, `_get_topics_members_with_existence`, `_build_lookups`; service `_search_vector`, `_merge_search_results`; and the `use_search_indicators_endpoint` flag (config field + constructor param + factory pass-throughs). `_filter_variables_by_existence` is legacy too, but its test is the place-like guard — re-point that test, then delete the method.
- **Keep the shared real-flow helpers:** `_filter_indicators_by_existence`, `_expand_topics_to_variables`, `_get_topics_members_with_existence_new`, `_get_variable_places_with_data`, `_get_topic_places_with_data`, `_ensure_place_variables_cached`, `_transform_search_indicators_response`.

**CLIENT-VISIBLE behavior change:** richer/correct search results (typeOf-identified topics and topics not in the local cache are no longer dropped); ordering, place type-mappings, and resolved-parent are preserved; place-like member-topic filtering is fixed.

Non-goals: NO `clients.py` module split (separate mechanical follow-up); NO structured output (4d); NO removal of `place_like_constraints`/`_constrained_vars.py` (externally blocked); NO adoption of `defaultThreshold`/`thresholdOverride` relevance filtering (deferred — adding new relevance-filtering behavior to a risky migration is out of scope).

## Capabilities

### New Capabilities
- `native-search-indicators`: the search tool serves results directly from the real `/api/nl/search-indicators` implementation (no legacy/shim degradation), preserving the full tool response contract (names, place type-mappings, resolved parent, score ordering) and place-like existence filtering, with the legacy search-vector path fully removed.

### Modified Capabilities
<!-- None of the existing archived specs cover the search path's internals. -->

## Impact

- **Code:** `services/search.py` (re-wire; delete `_search_vector`/`_merge_search_results`); `clients.py` (delete the legacy/shim chain + flag usage; fix `_check_topic_exists_recursive`; order-by-score in the transform); `config.py` (remove `use_search_indicators_endpoint`).
- **Tests:** rewrite `test_services.py::TestSearchIndicators` (~17, mock `client.search_indicators` + `fetch_entity_infos`); delete legacy client/flag tests (~18); the `TestDCClientFetchIndicatorsNew` suite (~20) **becomes the live spec** (kept); re-point the place-like guard test (`test_temp_constrained_vars.py`) off `_filter_variables_by_existence`. Net test count will drop (dead-path tests removed).
- **Risk:** HIGH (client-visible search behavior). Mitigations: the real flow is already test-covered (those tests become the contract); a contract test asserts the full `SearchResponse` shape (type-mappings, resolved parent, score order) is preserved; place-like preserved + the member-topic gap fixed; live-API re-probe done (no drift). Suite + server boot are the gate.
