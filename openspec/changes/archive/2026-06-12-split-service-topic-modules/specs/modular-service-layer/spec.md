## ADDED Requirements

### Requirement: The service layer is split by domain
The observations and search service logic SHALL live in separate modules, not a single flat `services.py`.

#### Scenario: services is a package split by domain
- **WHEN** the source tree is inspected
- **THEN** `datacommons_mcp/services/` is a package containing an observations module (with `get_observations` / `get_observations_paginated`) and a search module (with `search_indicators`), and the flat `services.py` no longer exists

#### Scenario: No cross-domain coupling is introduced
- **WHEN** the observations and search service modules are inspected
- **THEN** neither imports private helpers from the other (the domains remain independent)

### Requirement: The topic layer separates model from I/O
The in-memory topic model SHALL be separated from cache/network I/O.

#### Scenario: topics is a package split by concern
- **WHEN** the source tree is inspected
- **THEN** `datacommons_mcp/topics/` is a package with a model module (`Node`/`TopicVariables`/`TopicNodeData`/`TopicStore`) and a loader/I/O module (cache read/write, node-data fetch, `create_topic_store`), and the flat `topics.py` no longer exists

#### Scenario: The model module has no I/O dependency
- **WHEN** the topic model module is imported
- **THEN** it does not require the cache/network I/O code to be importable (the model can be used independently)

#### Scenario: The model→I/O import edge is one-directional
- **WHEN** the topic model module (`store`) is inspected for imports
- **THEN** it imports nothing from the loader/I/O module (`loader`); the only edge is `loader → store`, so no circular import is possible

### Requirement: Public import paths are preserved
Reorganizing into packages SHALL NOT break the public import surface that other modules and tests rely on.

#### Scenario: Existing public imports keep working
- **WHEN** code imports `from datacommons_mcp.services import get_observations, get_observations_paginated, search_indicators` or `from datacommons_mcp.topics import TopicStore, TopicVariables, read_topic_caches, create_topic_store`
- **THEN** those imports resolve via the package `__init__` re-exports, unchanged from before

#### Scenario: Behavior and suite are unchanged
- **WHEN** the full non-e2e test suite runs and the stdio server is booted after the split
- **THEN** all non-e2e tests pass (224) with no behavior change, and the server starts and registers both tools without error
