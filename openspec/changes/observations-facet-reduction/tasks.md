## 1. Shared ranking helper

- [ ] 1.1 In `services/observations.py`, extract the facet-ranking (the stats-gather over `byEntity` + the `max(...)` on `(place_coverage, obs_count, latest_date, -avg_index, src_id)`, lines ~169-211) into `rank_primary_facet(variable_data: ByVariable, date_filter) -> str | None`. Refactor `_process_sources_and_filter_observations` to call it (behavior-preserving — the full-path ranking is unchanged).
- [ ] 1.2 Confirm via existing tests that the refactor is behavior-preserving before adding new behavior.

## 2. Auto facet-selection

- [ ] 2.1 In `get_observations_paginated`, after `_validate_and_build_request` and BEFORE the main fetch, add auto-select GATED on: `request.child_place_type` AND `request.date` is the "all" sentinel AND no `source_override`/`source_ids` already set. (Confirm the exact "all" check against `ObservationDateType`/`date_filter`.)
- [ ] 2.2 Probe: build a `date="latest"` variant request (same variable/place/child_place_type), `fetch_obs_page` it, run `rank_primary_facet` on its `ByVariable` → `primary`. If the probe yields no facet (no data), skip auto-select (fall through to normal behavior).
- [ ] 2.3 Set the effective source to `[primary]`: set `request.source_ids = [primary]` (so `fetch_obs_page` sends `filter_facet_ids=[primary]`) AND ensure the downstream processing uses the single-source path for `primary` (route `_process_sources_and_filter_observations` via the `source_override=primary` branch, OR confirm a single-facet response ranks to `primary` trivially — pick whichever is exact and test it).
- [ ] 2.4 Leave single-place, explicit-override, `latest`/single-date, and date-range queries on the existing path (no probe).

## 3. Raise the place budget

- [ ] 3.1 `config.py`: `max_places` default `1000 → 5000` (update the field default + its description; keep `ge`/`le`). Note in the description that A-i's facet reduction lowered per-query memory.

## 4. Tests

- [ ] 4.1 `tests/test_services.py`: extract-helper unit test — `rank_primary_facet` over a hand-built multi-facet `ByVariable` returns the coverage-primary; ties fall through to latest-date/facet-order/src_id.
- [ ] 4.2 Auto-select path (mock `client.fetch_obs_page` to return a multi-facet `latest` response on the first call and a single-facet full response on the second): a `child_place_type` + `date="all"` + no-override query (a) issues the `latest` probe, (b) issues the second fetch with `request.source_ids == [primary]`, (c) returns the primary source's observations. Assert two fetches and the `source_ids` on the second.
- [ ] 4.3 Unchanged paths: single-place query → NO probe (one fetch); explicit `source_override` → NO probe; `date="latest"` and a date range → NO probe. Assert call counts.
- [ ] 4.4 Coverage-tie behavior: a `latest` response where two facets tie on coverage → assert the documented tiebreak (latest-date/facet-order) is what's selected (pins the accepted change).
- [ ] 4.5 `tests/` for config: `DC_MAX_PLACES` default is 5000; a ~3,238-place child query is NOT refused by the guardrail (mock `count_child_places`).
- [ ] 4.6 Confirm existing `TestGetObservations` + structured-output tests still pass.

## 5. Docs + verification

- [ ] 5.1 `docs/reference.md`: document auto source-selection for large child-place exports, the ~10× memory profile, the new `DC_MAX_PLACES=5000` default, and the coverage-tie caveat. Note streaming is not possible on the v2 API (so very large geographies past the series cap are still bounded by the guardrail until place-sharding lands).
- [ ] 5.2 `uv run --extra dev ruff format --check && ruff check && mypy src/datacommons_mcp && pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` → all pass.
- [ ] 5.3 (If DC_API_KEY available) manual sanity: a county-scale `date="all"` export completes with bounded memory and the same primary source as before. Commit per group; Gate 2 before docs/archive.
