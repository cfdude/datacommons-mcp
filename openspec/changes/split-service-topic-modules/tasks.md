## 1. Split `services.py` into a `services/` package

- [ ] 1.1 Create `datacommons_mcp/services/observations.py` with the observations domain: `get_observations`, `get_observations_paginated`, and their private helpers (`_validate_and_build_request`, `_fetch_all_metadata`, `_process_sources_and_filter_observations`, `_create_place_observation`, `_build_final_response`) + the imports they need.
- [ ] 1.2 Create `datacommons_mcp/services/search.py` with the search domain: `search_indicators`, `_SearchPlaceContext`, and the search privates (`_resolve_and_partition_places`, `_create_search_tasks`, `_validate_search_parameters`, `_resolve_places`, `_collect_all_dcids`, `_search_vector`, `_fetch_and_update_lookups`, `_merge_search_results`) + their imports.
- [ ] 1.3 Create `datacommons_mcp/services/__init__.py` re-exporting the public API: `get_observations`, `get_observations_paginated`, `search_indicators` (with `__all__`).
- [ ] 1.4 Delete the flat `datacommons_mcp/services.py`.
- [ ] 1.5 If a private helper is genuinely shared across the two domains (not expected per the audit), put it in `datacommons_mcp/services/_shared.py` and import from there in both — do NOT cross-import between `observations.py` and `search.py`.

## 2. Split `topics.py` into a `topics/` package

- [ ] 2.1 Create `datacommons_mcp/topics/store.py` with the model + pure predicates (NO I/O imports): `Node`, `TopicVariables`, `TopicNodeData`, `TopicStore`, `_flatten_variables_recursive`, AND `_is_topic_dcid` (it is a pure string predicate called by `TopicNodeData` methods at topics.py:69/73/80/88 — it MUST be in store.py or store→loader would cycle), AND the two prefix constants it/`_flatten` use: `_DCID_PREFIX_TOPIC`, `_DCID_PREFIX_SVPG`.
- [ ] 2.2 Create `datacommons_mcp/topics/loader.py` with the I/O: `read_topic_caches`, `read_topic_cache`, `_fetch_node_data`, `_save_topic_store_to_cache`, `_load_topic_store_from_cache`, `create_topic_store`, AND the I/O constants `_SOURCE_DIR`, `_TYPE_TOPIC`, `_DEFAULT_TOPIC_CACHE_DIR`, `_DEFAULT_TOPIC_CACHE_PATHS` — importing the model + `_flatten_variables_recursive` + `_is_topic_dcid` from `datacommons_mcp.topics.store`. `loader → store` MUST be the only import edge (store imports nothing from loader).
- [ ] 2.3 Create `datacommons_mcp/topics/__init__.py` re-exporting the public API: `Node`, `TopicVariables`, `TopicNodeData`, `TopicStore`, `read_topic_caches`, `read_topic_cache`, `create_topic_store` (with `__all__`).
- [ ] 2.4 Delete the flat `datacommons_mcp/topics.py`.

## 3. Repoint the one private test import

- [ ] 3.1 In `tests/test_services.py`, change the import of `_validate_and_build_request` from `datacommons_mcp.services` to `datacommons_mcp.services.observations`. Leave the public imports (`get_observations`, `search_indicators`) as-is (they resolve via the package `__init__`).

## 4. Verification & integration

- [ ] 4.1 Import smoke (forces a cycle to surface deterministically): `uv run python -c "import datacommons_mcp.services.observations; import datacommons_mcp.services.search; import datacommons_mcp.topics.store; import datacommons_mcp.topics.loader; import datacommons_mcp.clients; import datacommons_mcp.servers.base; import datacommons_mcp.fastmcp_server; print('ok')"`.
- [ ] 4.2 Confirm public imports still resolve: `from datacommons_mcp.services import get_observations, get_observations_paginated, search_indicators` and `from datacommons_mcp.topics import TopicStore, TopicVariables, read_topic_caches, create_topic_store`.
- [ ] 4.3 Final gate: `uv run ruff format --check && uv run ruff check && uv run pytest -m "not e2e"` → 224 pass (no drop); `uv lock --check` consistent; server boots via `python datacommons_mcp/run_server.py` (EOF) with both tools registered.
- [ ] 4.4 Commit per logical group (conventional commits), then proceed to Gate 2 (Superpowers code review) before finalizing.
