## Context

`get_observations` takes one parent `place_dcid` (or `place_name`) plus an optional `child_place_type`; the only way to fan out to many places is a child-place query, which the DC API expands server-side. The service (`services/observations.py`) builds the request and calls `client.fetch_obs_page` once; the library returns the whole dataset, materialized in memory ([[observations-streaming-reality]]). `clients/entities.py::child_place_type_exists` already calls `dc.node.fetch_place_children(place_dcids=parent, children_type=child_type, as_dict=True)` and reads `len(response.get(parent, []))` — the exact count we need, cheaply (place DCIDs only, no observations). A cheap row count via `select` is NOT possible (the typed response model rejects reduced selects — verified).

## Decisions

**1. Gate on child-place COUNT, not row count.** Place count is the dominant memory driver (probe: 57 states ≈ 90 MB; 3,143 counties ≈ 1 GB) and is the only magnitude signal obtainable cheaply (the API's `select` can't return a value-less count). Row count = places × dates × facets is unknowable without the full fetch. *Alternative (raw-JSON count via base.post):* rejected — more plumbing, and place count already isolates the OOM cases (counties/tracts). The threshold is intentionally conservative to cover the per-place variance.

**2. `DC_MAX_PLACES` default 1000.** Keeps peak RAM in the low-hundreds-of-MB (≈ 1/3 of the all-counties peak) while allowing states/metros/a few hundred places. Configurable so a high-RAM machine can raise it (or a cautious one lower it). Lives on `AppConfig` (output/runtime config), like `screen_row_threshold`.

**3. New `ResultTooLargeError(ValueError)`** — semantically distinct from `InvalidInputError` (the input is valid; the *result* is too big), and a future hook for item A (streaming could catch it to route differently). Add it to `_CLIENT_FACING_ERRORS` in `servers/common.py` so `tool_error_boundary` surfaces its message rather than masking it.

**4. Guardrail location: the service, pre-fetch.** In the `get_observations` service path, right after the request is built and BEFORE `fetch_obs_page`, when `child_place_type` is set: `n = await client.count_child_places(parent_dcid, child_place_type)`; if `n > config.max_places`, raise `ResultTooLargeError(...)`. Single-place queries skip the check. *Alternative (in the tool):* rejected — the service owns the fetch and already has the client + request.

**5. Message is actionable + specific.** e.g. `f"This query spans {n} {child_place_type} places under {parent}, which would build a very large response in server memory (the full result is materialized before writing). The limit is DC_MAX_PLACES={limit}. Narrow it — a specific date or range, a coarser place type, or fewer places — or wait for streaming support."`

## Risks / Trade-offs

- **Refuses some currently-succeeding queries** (all-counties works today by using ~1 GB) → intended stopgap; reversible via `DC_MAX_PLACES`; resolved by item A (streaming). Flag clearly in the message + docs.
- **Place count is a proxy, not exact memory** (per-place cost varies with dates/facets) → conservative default + configurability mitigate; A is the precise fix.
- **One extra cheap call** (`fetch_place_children`) per child-place query → negligible (place DCIDs only) and only on the fan-out path.

## Migration Plan

1. `config.py`: add `max_places: int` (alias `DC_MAX_PLACES`, default 1000, bounded ≥1) to `AppConfig`.
2. `exceptions.py`: add `ResultTooLargeError(_ErrorStrMixin, ValueError)`.
3. `servers/common.py`: add `ResultTooLargeError` to `_CLIENT_FACING_ERRORS`.
4. `clients/entities.py`: add `count_child_places(parent_dcid, child_place_type) -> int` (wrap `fetch_place_children`; return `len(response.get(parent_dcid, []))`).
5. `services/observations.py`: in the `get_observations` service path, pre-fetch, when `child_place_type` is set, count children and raise `ResultTooLargeError` if over `config.max_places`. (Config is available via the lifespan/`get_config`; confirm the service has access or thread it through.)
6. Tests + `docs/reference.md` note.
7. Gate: ruff + mypy + full suite + coverage ≥ 80.

**Rollback:** revert; config/guardrail only, no data migration. Note: the config plumbing (how the service reads `max_places`) is the one integration detail to verify in apply — `get_config(ctx)` is available in the tool; the service may need `max_places` passed in.
