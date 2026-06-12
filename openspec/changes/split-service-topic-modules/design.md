## Context

`services.py` (838 LOC) holds two independent service domains (observations, search) and `topics.py` (543 LOC) holds the topic model plus its cache/network I/O. An architecture audit verified clean boundaries: services.py has no cross-domain coupling (the two public entry points and their private helpers don't reference each other), and topics.py separates dataclasses (`Node`/`TopicVariables`/`TopicNodeData`/`TopicStore` + a pure `_flatten_variables_recursive`) from I/O (`read_topic_cache(s)`, `_fetch_node_data`, `_save/_load_topic_store_from_cache`, `create_topic_store`). This is the first, safest slice of the decomposed #4.

## Goals / Non-Goals

**Goals:**
- Two focused service modules (observations, search) and a topics package separating model from I/O.
- Preserve the public import surface and all behavior; suite stays green (224).

**Non-Goals:**
- No `clients.py` split (#4c, after the search migration), no `utils/`→`services/` reclassification (deferred), no error model (#4b), no structured output (#4d), no search migration (#4c).
- No logic changes; no env/output changes.

## Decisions

**1. Use package `__init__` re-exports to keep public import paths stable.** `services/__init__.py` re-exports `get_observations`, `get_observations_paginated`, `search_indicators`; `topics/__init__.py` re-exports the model classes + `read_topic_caches`/`read_topic_cache`/`create_topic_store`. External importers (`servers/*`, `clients.py`, tests) then need no change. *Alternative:* update every importer to the new submodule paths — rejected as more churn and more risk for a mechanical move; the deeper path cleanup can ride along with #5's `src/` reorg.

**2. Re-export only the PUBLIC API; repoint the one private test import.** `tests/test_services.py` imports the private `_validate_and_build_request`. Rather than leak a private through the package root, repoint that single import to `datacommons_mcp.services.observations`. Keeps the public surface clean.

**3. File layout:**
- `services/__init__.py` (re-exports) · `services/observations.py` (`get_observations`, `get_observations_paginated` + their `_validate_and_build_request`/`_fetch_all_metadata`/`_process_sources_and_filter_observations`/`_create_place_observation`/`_build_final_response`) · `services/search.py` (`search_indicators` + `_SearchPlaceContext` and the search privates).
- `topics/__init__.py` (re-exports) · `topics/store.py` (the dataclasses + `_flatten_variables_recursive` + `_is_topic_dcid` + `_DCID_PREFIX_TOPIC`/`_DCID_PREFIX_SVPG`) · `topics/loader.py` (cache/I/O + `create_topic_store` + the I/O constants, importing model/`_flatten_variables_recursive`/`_is_topic_dcid` from `topics.store`).

**Invariant (prevents the circular import):** `store.py` = model dataclasses + the pure predicate `_is_topic_dcid` (called by `TopicNodeData` methods) + `_flatten_variables_recursive` + the two `_DCID_PREFIX_*` constants. EVERYTHING else (cache paths, `_TYPE_TOPIC`, fetch/save/load, `read_topic_cache(s)`, `create_topic_store`) → `loader.py`. `read_topic_cache` lives in loader and imports `_flatten_variables_recursive`/`_is_topic_dcid` from store rather than duplicating them. `loader → store` is the ONLY import edge.

**4. Shared helpers:** the audit found none across the two service domains. If apply surfaces a genuinely shared private, place it in a small `services/_shared.py` rather than cross-importing between domains. (Not expected.)

## Risks / Trade-offs

- **A hidden cross-domain reference breaks the split** → Mitigation: after moving, run the suite + an import smoke; if `services/search.py` needs an observations private (or vice versa), surface it to `_shared.py`.
- **A circular import between `topics/store.py` and `topics/loader.py`** → Mitigation: `loader` imports from `store` (one direction only); `store` imports nothing from `loader`. Verify with an import smoke.
- **An importer relied on a name not re-exported** → Mitigation: enumerate the public names from the current modules and re-export exactly those; grep all importers (already mapped: `servers/observations.py`, `servers/search.py`, `clients.py`, `test_services.py`, `test_topics.py`, `test_e2e.py`).

## Migration Plan

1. Create `services/` package: move observations code → `observations.py`, search code → `search.py`, add `__init__.py` re-exports; delete `services.py`.
2. Create `topics/` package: model → `store.py`, I/O → `loader.py` (importing model from `store`), add `__init__.py` re-exports; delete `topics.py`.
3. Repoint `tests/test_services.py`'s private import to `services.observations`.
4. Import smoke + `ruff` + non-e2e suite (224) + server boot.

**Rollback:** revert the commits; the split is pure reorganization with no data/migration involved.
