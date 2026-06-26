## ADDED Requirements

### Requirement: Child-place queries are size-gated before fetching
`get_observations` SHALL estimate the place count of a `child_place_type` query before fetching observations, and refuse queries that exceed the configured place budget.

#### Scenario: A query over too many places is refused with guidance
- **WHEN** `get_observations` is called with a `child_place_type` whose parent has more child places than `DC_MAX_PLACES`
- **THEN** the tool raises an actionable `ToolError` (from `ResultTooLargeError`) BEFORE the observation fetch, and the message states the place count, names the `DC_MAX_PLACES` limit, and suggests narrowing (place type / date / fewer places) or notes streaming support is coming — and no large response is materialized

#### Scenario: A query within the budget proceeds normally
- **WHEN** the parent's child-place count is at or below `DC_MAX_PLACES`
- **THEN** the query runs as before (no behavior change)

#### Scenario: Single-place and explicit queries are not gated
- **WHEN** `get_observations` is called without `child_place_type` (a single place)
- **THEN** no place-count gate is applied (a single place cannot fan out to a large response)

### Requirement: The place budget is configurable
The place budget SHALL be configurable via `DC_MAX_PLACES`.

#### Scenario: DC_MAX_PLACES sets the limit
- **WHEN** `DC_MAX_PLACES` is set in the environment
- **THEN** `AppConfig.max_places` reflects it (default 1000), and the guardrail uses that value

### Requirement: The size error is actionable, not masked
`ResultTooLargeError` SHALL surface its message to the client.

#### Scenario: The guardrail message reaches the client
- **WHEN** `ResultTooLargeError` is raised inside a tool
- **THEN** the `tool_error_boundary` maps it to a `ToolError` carrying its message (it is in the client-facing error set), not the generic masked message

### Requirement: The count helper is cheap
The child-place count SHALL come from a lightweight call, not a full observation fetch.

#### Scenario: Counting uses fetch_place_children
- **WHEN** the guardrail needs the child-place count
- **THEN** it uses `client.count_child_places(parent, child_place_type)` (wrapping `fetch_place_children`), which does not fetch observations
