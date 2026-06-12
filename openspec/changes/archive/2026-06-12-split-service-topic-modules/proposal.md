## Why

Two core modules are oversized god modules: `services.py` (838 LOC) mixes the **observations** and **search** service domains in one flat file, and `topics.py` (543 LOC) conflates the in-memory **model** (`TopicStore` and friends) with **cache/network I/O**. An architecture audit confirmed clean split boundaries: the two service domains have **no cross-domain coupling**, and the topic model/IO layers are cleanly separable.

This is slice 1 of the decomposed `modularize-core` work (#4), chosen first because it is **mechanical and behavior-preserving** — pure module reorganization with the test suite + server boot as the safety net. It shrinks the surface for the riskier later slices (error model #4b, search migration + clients.py split #4c, structured output #4d).

## What Changes

- **Split `services.py` into a `services/` package:** `services/observations.py` (the `get_observations` / `get_observations_paginated` domain + its private helpers), `services/search.py` (the `search_indicators` domain + its helpers), and `services/__init__.py` re-exporting the public API.
- **Split `topics.py` into a `topics/` package:** `topics/store.py` (the `Node`/`TopicVariables`/`TopicNodeData`/`TopicStore` model + pure parsing), `topics/loader.py` (cache read/write + node-data fetch + `create_topic_store`), and `topics/__init__.py` re-exporting the public API.
- **Preserve public import paths** via the package `__init__` re-exports, so external importers (`servers/observations.py`, `servers/search.py`, `clients.py`, tests) keep working unchanged.
- **Repoint one private test import:** `tests/test_services.py` imports the private `_validate_and_build_request` — point it at `services.observations` (rather than re-exporting a private from the package root).

**BREAKING (internal only):** the internal file layout changes; the public import surface (`datacommons_mcp.services.*`, `datacommons_mcp.topics.*`) is unchanged. No tool behavior, env vars, or outputs change.

Non-goals (other #4 slices): NOT splitting `clients.py` (that follows the search migration, #4c); NOT reclassifying `utils/` orchestrators into `services/` (deferred); NOT the error model (#4b), structured output (#4d), or the search-vector→search-indicators migration (#4c). Zero behavior change here.

## Capabilities

### New Capabilities
- `modular-service-layer`: the service and topic layers are organized into focused, single-responsibility modules (observations vs search; topic model vs topic I/O), with the public import surface preserved and behavior unchanged.

### Modified Capabilities
<!-- None — module organization was not covered by the existing specs. -->

## Impact

- **Code:** `services.py` → `services/{__init__,observations,search}.py`; `topics.py` → `topics/{__init__,store,loader}.py`. Internal imports within the split modules updated; external importers unchanged (re-exports).
- **Tests:** `tests/test_services.py`'s one private import repointed to `services.observations`; all other test imports unchanged.
- **Risk:** low — pure reorganization, no logic change. The 224-test suite + server boot are the regression gate. The audit confirmed no cross-domain coupling, so the split is clean.
- **Naming note:** this introduces a `services/` package alongside the existing `servers/` (the tool layer). The similar names are tolerated here; the `servers/`→`tools/` rename that disambiguates them is part of #5 (`src-layout-and-packaging`).
