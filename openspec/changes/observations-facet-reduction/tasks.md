## 1. Shared ranking helper

- [ ] 1.1 In `services/observations.py`, extract the facet-ranking (the stats-gather over `byEntity` + the `max(...)` on `(place_coverage, obs_count, latest_date, -avg_index, src_id)`, lines ~169-211) into `rank_primary_facet(variable_data: ByVariable, date_filter) -> tuple[str | None, dict[str,int]]` returning `(primary_id, source_places_found_counts)`. Refactor `_process_sources_and_filter_observations` to call it (behavior-preserving — the full-path ranking + `alternative_source_counts` unchanged).
- [ ] 1.2 Confirm via existing tests that the refactor is behavior-preserving before adding new behavior.

## 2. Auto facet-selection (probe-carry-forward)

- [ ] 2.1 In `get_observations_paginated`, insert auto-select AFTER the size guardrail (C3 — so a refused query never probes) and BEFORE the main fetch, GATED (C5) on: `request.child_place_type AND request.date_type == ObservationDateType.ALL AND request.date_filter is None AND not request.source_ids`. (Single date and range both set `date_type=ALL` with a non-None `date_filter` → correctly excluded.)
- [ ] 2.2 Probe: build a `date="latest"` variant request (same variable/place/child_place_type), `fetch_obs_page` it, run `rank_primary_facet` on its `ByVariable` → `(primary, per_source_counts)`. KEEP the probe's full place-dcid set (`byEntity.keys()`) and `per_source_counts`. If no facet (no data), skip auto-select (fall through to normal behavior). Then discard the probe response (retain only the small extracted data).
- [ ] 2.3 Set `request.source_ids = [primary]` (so `fetch_obs_page` sends `filter_facet_ids=[primary]`; `_process_sources_and_filter_observations` auto-routes via the override branch since `source_override = request.source_ids[0] if request.source_ids else None` at services/observations.py:274). Do the main fetch.
- [ ] 2.4 **Reconstruct (C1+C2):** pass the kept `(full_place_dcids, alternative_source_counts=per_source_counts without primary)` into `_build_final_response` for the reduced path so it (a) re-adds places present in the probe but absent from the filtered result as empty-series `PlaceObservation`s (mirroring the non-reduced `_create_place_observation(None)` at 299-310), and (b) populates `alternative_sources` from the carried counts. Verify the reduced result's place set + `alternative_sources` equal the non-reduced path's.
- [ ] 2.5 Leave single-place, explicit-override, `latest`/single-date, and date-range queries on the existing path (no probe). `get_observations` (non-paginated) is NOT modified.

## 3. Raise the place budget

- [ ] 3.1 `config.py`: `max_places` default `1000 → 5000` (update the field default + its description; keep `ge`/`le`). Note in the description that A-i's facet reduction lowered per-query memory.

## 4. Tests

- [ ] 4.1 `rank_primary_facet` unit test over a hand-built multi-facet `ByVariable`: returns the coverage-primary + the per-source counts; ties fall through to latest-date/facet-order/src_id.
- [ ] 4.2 Auto-select path (mock `fetch_obs_page`: multi-facet `latest` response first, single-facet full response second): `child_place_type` + `date="all"` + no-override (a) issues the `latest` probe, (b) issues the 2nd fetch with `request.source_ids == [primary]`, (c) returns the primary obs. Assert two fetches + the `source_ids`.
- [ ] 4.3 **Output-equivalence (C1):** construct a `latest` probe response with a place that has ONLY a non-primary facet, and a filtered full response that OMITS that place → assert the reduced result still contains that place with an empty time-series (same place set as non-reduced).
- [ ] 4.4 **alternative_sources (C2):** assert the reduced result's `alternative_sources` is populated from the probe (matches what the non-reduced path would report), not empty.
- [ ] 4.5 **Probe-after-guardrail (C3):** a `child_place_type` `date="all"` query over `max_places` (mock `count_child_places` high) raises `ResultTooLargeError` and issues ZERO `fetch_obs_page` calls.
- [ ] 4.6 Unchanged paths (no probe; assert call counts): single-place; explicit `source_override`; `date="latest"`; single date (`date_filter` set); a date range.
- [ ] 4.7 Coverage-tie: a `latest` response where two facets tie on coverage → assert the documented tiebreak (latest-date/facet-order) selection (pins the accepted change).
- [ ] 4.8 Config: `DC_MAX_PLACES` default is 5000; a ~3,238-place child query is NOT refused (mock `count_child_places`). Check no test hardcodes the old `1000` default.
- [ ] 4.9 Confirm existing `TestGetObservations` + structured-output tests still pass (they use the non-paginated path / explicit `max_places`, so unaffected).

## 5. Docs + verification

- [ ] 5.1 `docs/reference.md`: document auto source-selection for large child-place exports, the ~10× memory profile, the new `DC_MAX_PLACES=5000` default, and the coverage-tie caveat. Note streaming is not possible on the v2 API (so very large geographies past the series cap are still bounded by the guardrail until place-sharding lands).
- [ ] 5.2 `uv run --extra dev ruff format --check && ruff check && mypy src/datacommons_mcp && pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` → all pass.
- [ ] 5.3 (If DC_API_KEY available) manual sanity: a county-scale `date="all"` export completes with bounded memory and the same primary source as before. Commit per group; Gate 2 before docs/archive.
