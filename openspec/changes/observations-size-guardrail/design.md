## Context

`get_observations` takes one parent `place_dcid` (or `place_name`) plus an optional `child_place_type`; the only way to fan out to many places is a child-place query, which the DC API expands server-side. The service (`services/observations.py`) builds the request and calls `client.fetch_obs_page` once; the library returns the whole dataset, materialized in memory ([[observations-streaming-reality]]). `clients/entities.py::child_place_type_exists` already calls `dc.node.fetch_place_children(place_dcids=parent, children_type=child_type, as_dict=True)` and reads `len(response.get(parent, []))` — the exact count we need, cheaply (place DCIDs only, no observations). A cheap row count via `select` is NOT possible (the typed response model rejects reduced selects — verified).

## Decisions

**1. Gate on child-place COUNT, not row count.** Place count is the dominant memory driver (probe: 57 states ≈ 90 MB; 3,143 counties ≈ 1 GB) and is the only magnitude signal obtainable cheaply (the API's `select` can't return a value-less count). Row count = places × dates × facets is unknowable without the full fetch. *Alternative (raw-JSON count via base.post):* rejected — more plumbing, and place count already isolates the OOM cases (counties/tracts). The threshold is intentionally conservative to cover the per-place variance.

**2. `DC_MAX_PLACES` default 1000.** Keeps peak RAM in the low-hundreds-of-MB (≈ 1/3 of the all-counties peak) while allowing states/metros/a few hundred places. Configurable so a high-RAM machine can raise it (or a cautious one lower it). Lives on `AppConfig` (output/runtime config), like `screen_row_threshold`.

**3. New `ResultTooLargeError(ValueError)`** — semantically distinct from `InvalidInputError` (the input is valid; the *result* is too big), and a future hook for item A (streaming could catch it to route differently). Add it to `_CLIENT_FACING_ERRORS` in `tools/common.py` so `tool_error_boundary` surfaces its message rather than masking it.

**4. Guardrail location: the service, pre-fetch.** In the `get_observations` service path, right after the request is built and BEFORE `fetch_obs_page`, when `child_place_type` is set: `n = await client.count_child_places(parent_dcid, child_place_type)`; if `n > config.max_places`, raise `ResultTooLargeError(...)`. Single-place queries skip the check. *Alternative (in the tool):* rejected — the service owns the fetch and already has the client + request.

**5. Message is actionable + specific.** e.g. `f"This query spans {n} {child_place_type} places under {parent} (counting all child places, not only those with data), which would build a very large response in server memory (the full result is materialized before writing). The limit is DC_MAX_PLACES={limit}. Narrow it — a specific date or range, a coarser place type, or fewer places — or wait for streaming support."` The "counting all child places" phrasing discloses the sparse-variable false-positive.

## Risks / Trade-offs

- **Refuses some currently-succeeding queries** (all-counties works today by using ~1 GB) → intended stopgap; reversible via `DC_MAX_PLACES`; resolved by item A (streaming). Flag clearly in the message + docs.
- **Place count is a proxy, not exact memory** (per-place cost varies with dates/facets), and it counts ALL geographic children of the type — NOT only those with data for the variable. So a **sparse** variable over a large geography (e.g. data for 40 of `country/USA`'s ~3,238 counties) is refused even though the real response is small (a false positive). This is memory-safe (conservative) but a usability regression; the error message acknowledges it ("counts all child places, not only those with data"), and item A removes the need for the gate entirely.
- **The gate does NOT bound the date/facet dimension.** A `date="all"`, dense/multi-facet/multi-decade query over a few hundred places can still approach high RAM and won't be caught by place count alone. The conservative default helps but isn't universal; A is the precise fix. (The tool docstring already advises against `date="all"` in child-place mode.)
- **Completeness verified:** `fetch_place_children(country/USA, County)` returns **3,238** (not a round/capped page), confirming `count_child_places` reports the true total — so the gate won't silently under-count and leak.
- **One extra cheap call** (`fetch_place_children`) per child-place query → negligible (place DCIDs only) and only on the fan-out path.

## Migration Plan

1. `config.py`: add `max_places: int` (alias `DC_MAX_PLACES`, default 1000, bounded ≥1) to `AppConfig`.
2. `exceptions.py`: add `ResultTooLargeError(_ErrorStrMixin, ValueError)`.
3. `tools/common.py`: add `ResultTooLargeError` to `_CLIENT_FACING_ERRORS`.
4. `clients/entities.py`: add `count_child_places(parent_dcid, child_place_type) -> int` (wrap `fetch_place_children`; return `len(response.get(parent_dcid, []))`).
5. `services/observations.py`: in the `get_observations` service path, pre-fetch, when `child_place_type` is set, count children and raise `ResultTooLargeError` if over `config.max_places`. (Config is available via the lifespan/`get_config`; confirm the service has access or thread it through.)
6. Tests + `docs/reference.md` note.
7. Gate: ruff + mypy + full suite + coverage ≥ 80.

**Rollback:** revert; config/guardrail only, no data migration. Note: the config plumbing (how the service reads `max_places`) is the one integration detail to verify in apply — `get_config(ctx)` is available in the tool; the service may need `max_places` passed in.
