## Why

`get_observations` materializes the **entire** result in the MCP-server process before writing the file, and the raw API response is much larger than the written CSV (it holds every source/facet before the service filters to one primary source per place). Measured ([[observations-streaming-reality]]): a single ordinary query — `Count_Person` for **all US counties × all years** — pulls **532,944 raw observations** and peaks at **~1 GB RSS** (456 MB Python heap) to produce a 4 MB file. Extrapolated to ~250k written rows (a real company use case), peak RAM is **multiple GB → OOM/thrash** on most machines.

This is item C — the **count-first guardrail**: cheaply estimate the query's magnitude *before* the expensive fetch, and refuse (with actionable guidance) the queries that would blow up memory, instead of letting the server OOM. It is the immediate stopgap; **true streaming (the separate `observations-true-streaming` epic, item A) is the real fix** and will turn this refusal into a streaming export.

A cheap row-count via the API's `select` is not available (the DC client's typed response model rejects any reduced `select`). But the dominant memory driver is the **place count**, and that *is* cheap to get: explicit place lists are already known, and child-place queries (the only way to fan out to many places) can count children via the existing `fetch_place_children` path.

## What Changes

- **Add a config knob `DC_MAX_PLACES`** (`AppConfig`, default **1000**) — the maximum number of places a single `get_observations` call may span before it is refused. Calibrated from the probe (57 states ≈ 90 MB OK; ~3,238 counties ≈ 1 GB), 1000 keeps peak RAM bounded for typical (latest/bounded-date) queries — it caps the *place* dimension, not the date/facet dimension, so a `date="all"` dense query over a few hundred places can still be heavy (item A is the precise fix). Configurable so it can be tuned to the machine.
- **Add a client helper** `count_child_places(parent_dcid, child_place_type) -> int` (wraps `fetch_place_children`, mirroring `child_place_type_exists`).
- **Guardrail in the observations service:** for a `child_place_type` query, count the children before fetching; if it exceeds `DC_MAX_PLACES`, raise a new domain error `ResultTooLargeError` with an actionable message (the place count, the `DC_MAX_PLACES` knob, and guidance: narrow by place type / date / fewer places, or wait for streaming). Single-place / explicit queries are not gated (they can't fan out).
- **Surface it as an actionable ToolError:** add `ResultTooLargeError` to the error boundary's client-facing set so its guidance reaches the user (not masked).

**CLIENT-VISIBLE change (intended):** a child-place query spanning more than `DC_MAX_PLACES` places now returns a clear ToolError with guidance instead of (today) succeeding at the cost of ~1 GB+ RAM. This is a deliberate stopgap — those queries become streamable exports once item A lands.

Non-goals: NO streaming/pagination rebuild (that's `observations-true-streaming`, item A); NO change to queries within the limit; NO exact row-count estimate (place count is the cheap proxy; the threshold is conservative).

## Capabilities

### New Capabilities
- `observations-size-guardrail`: `get_observations` estimates a child-place query's place count up front and refuses (with actionable guidance) queries that would exceed a configurable place budget, preventing the server from materializing multi-GB responses in memory.

## Impact

- **Code:** `config.py` (`DC_MAX_PLACES`); `clients/entities.py` (`count_child_places`); `services/observations.py` (the pre-fetch guardrail); `exceptions.py` (`ResultTooLargeError`); `tools/common.py` (add it to `_CLIENT_FACING_ERRORS`).
- **Tests:** child count over the limit → `ToolError` with the guidance substring; under the limit → proceeds; single-place query → no gate; the count helper.
- **Docs:** note the limit + `DC_MAX_PLACES` in `docs/reference.md`.
- **Risk:** LOW–MEDIUM. It refuses some currently-succeeding (but memory-dangerous) queries — intended, and reversible by raising `DC_MAX_PLACES`. The cheap pre-count adds one `fetch_place_children` call to child-place queries.
