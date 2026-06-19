## Context

A read-only trace established the real-vs-shim picture. The native flow (`DCClient.search_indicators` → `_fetch_indicators_new` → `_transform_search_indicators_response`) builds typed `SearchTopic`/`SearchVariable` (dcid, description, alternate_descriptions, places_with_data, member info), identifies topics via `typeOf` AND prefix, and does existence-filtering/topic-expansion/name-lookups internally. The shim (`fetch_indicators` → client `_search_vector` → `_call_search_indicators_temp` → `_transform_search_indicators_to_svs_format`) flattens to legacy SV/CosineScore, re-sorts by score, and (in client `_search_vector`) identifies topics by prefix AND requires presence in the local topic store — silently dropping `typeOf`-topics and store-absent topics. The live `/api/nl/search-indicators` returns results already in score-descending order (verified). This is the keystone slice 4c.

## Goals / Non-Goals

**Goals:**
- Serve search from the native flow; delete the legacy/shim chain + flag; preserve the full tool contract (names, `dcid_place_type_mappings`, `resolved_parent_place`, score ordering) and place-like filtering.

**Non-Goals:**
- No `clients.py` module split (separate mechanical follow-up), no structured output (4d), no `place_like_constraints` removal, no `defaultThreshold` adoption.

## Decisions

**1. The service delegates result-finding but still resolves place metadata.** New wiring in `services/search.py::search_indicators`: keep `_resolve_and_partition_places`, `_resolve_places`, `_create_search_tasks`, `_validate_search_parameters`; replace the `_search_vector` call with `client.search_indicators(search_tasks=..., per_search_limit=..., include_topics=...)`; **still call `client.fetch_entity_infos` for the place DCIDs** (parent + resolved query places) to build `dcid_place_type_mappings` and `resolved_parent_place`; merge the native result's `dcid_name_mappings` with place names into the final `SearchResponse`. *Rationale:* `client.search_indicators` returns only names/topics/variables; the place type-map is contractual (`get_observations` docs reference it) and resolved-parent is part of the response. *Alternative (return client result directly):* rejected — drops two contractual fields.

**2. Preserve score-descending ordering in the native transform.** The built `SearchTopic`/`SearchVariable` carry no score field, so the sort MUST operate on the raw API result dicts: in `_transform_search_indicators_response`, sort each `index_result["results"]` by `indicator.get("score", 0.0)` descending before the model-building loop. This is **defensive/robust, not a behavior fix** — the live endpoint is already score-ranked and the models drop score, so observable order is unchanged; the explicit sort just removes reliance on implicit API order. The sort is **per-search**. Across multiple search tasks, the final merge (dedup, first-occurrence wins) follows the order the endpoint returns its query results in — the endpoint is authoritative for ranking. The legacy shim's "place-specific task first" cross-task ordering is intentionally NOT preserved (Gate-2 finding I-1): data is unaffected (each indicator carries `places_with_data`); only cross-task presentation order changes, and forcing legacy order back on top would fight the migration's intent. *Alternative (rebuild legacy task order):* rejected — re-imposes a shim artifact on the authoritative endpoint ranking.

**3. Close the place-like member-topic gap.** `_check_topic_exists_recursive` reads only `variable_cache`; make it union `_place_like_statvar_store` (consistent with `_get_variable_places_with_data`/`_get_topic_places_with_data`), so the native flow's member-topic existence filtering matches the legacy behavior. Small, in-scope correctness fix.

**4. Deletion set (legacy-only, caller-verified) + kept helpers.** Delete: client `search_svs`, `_call_search_indicators_temp`, `_transform_search_indicators_to_svs_format`, `fetch_indicators`, client `_search_vector`, `_filter_topics_by_existence`, `_get_topics_members_with_existence`, `_build_lookups`, `_filter_variables_by_existence` (after re-pointing its test); service `_search_vector`, `_merge_search_results`; config/client `use_search_indicators_endpoint`. Keep (native flow uses them): `_filter_indicators_by_existence`, `_expand_topics_to_variables`, `_get_topics_members_with_existence_new`, `_get_variable_places_with_data`, `_get_topic_places_with_data`, `_ensure_place_variables_cached`, `_transform_search_indicators_response`, plus the place-like scaffolding.

**5. Defer `defaultThreshold`.** The native flow ignores the endpoint's `defaultThreshold`/`thresholdOverride`. Adopting score-threshold filtering is a *new behavior*, not part of completing the migration; defer it (its own small change) to keep this risky migration focused.

## Risks / Trade-offs

- **A client-visible field/regression slips through** → Mitigation: a response-contract test asserts the full `SearchResponse` (names, `dcid_place_type_mappings`, `resolved_parent_place`, score order, topics/variables) is populated; the native flow's existing `TestDCClientFetchIndicatorsNew` tests become the live contract.
- **Wrongly deleting a shared helper** → Mitigation: each deletion was caller-verified to be legacy-only; the shared existence/expansion helpers are explicitly kept; `_filter_variables_by_existence`'s place-like guard test is re-pointed (not deleted) to `_get_variable_places_with_data`.
- **Topic-surfacing change alters results** → This is the intended improvement (no longer dropping typeOf/store-absent topics); the contract test asserts such a topic surfaces.

## Migration Plan

1. `services/search.py`: re-wire `search_indicators` to `client.search_indicators` + place-side `fetch_entity_infos`; delete `_search_vector`/`_merge_search_results`.
2. `clients.py`: order-by-score in `_transform_search_indicators_response`; fix `_check_topic_exists_recursive` to union place-like; delete the legacy/shim methods; remove the flag usage.
3. `config.py`: remove `use_search_indicators_endpoint` (field + factory pass-throughs).
4. Tests: rewrite `test_services.py::TestSearchIndicators` (mock `client.search_indicators` + `fetch_entity_infos`); delete legacy/flag/shim tests; re-point the place-like guard; add a response-contract test; keep `TestDCClientFetchIndicatorsNew`.
5. Gate: ruff + non-e2e suite + server boot; live `search_indicators` smoke if a key is available.

**Rollback:** revert the commits; no data/migration involved.
