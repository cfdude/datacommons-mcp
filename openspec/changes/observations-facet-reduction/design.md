## Context

`get_observations_paginated` (services/observations.py:330) builds an `ObservationRequest` via `_validate_and_build_request`, calls `client.fetch_obs_page(request)` (which passes `filter_facet_ids=request.source_ids` to the v2 API, clients/observations.py:36/42), then `_build_final_response` → `_process_sources_and_filter_observations` (services/observations.py:140). That function: with `source_override`, early-returns filtering to that facet per place (lines 149-167); else ranks all facets globally by `(place_coverage, total_obs_count, latest_date, -avg_facet_index, src_id)` (199-211) and keeps ONLY the primary source per place, **dropping places without it** (222-232). So the rendered output is already "one source per place, places lacking the primary excluded."

The v2 API has no pagination (confirmed against REST + Python v2 docs and live) and hard-rejects >~tens-of-thousands of series with HTTP 500. The memory cost is the multi-facet raw response (~11× the written rows). `filter_facet_ids` lets the API return a chosen facet only — measured ~10× memory reduction, identical output (since today already collapses to one primary).

## Decisions

**1. Auto-select = "compute the primary facet cheaply, then take the existing `source_override` path."** For a `child_place_type` + `date="all"` + no-override query: (a) probe at `date="latest"`, rank facets, pick primary; (b) set the request's effective source to `[primary]` so `fetch_obs_page` sends `filter_facet_ids=[primary]` AND `_process_sources_and_filter_observations` runs its exact single-source path. Output is identical to today modulo the tiebreak caveat. *Why reuse override path:* it's the already-correct, already-tested single-facet code.

**2. Probe at `date="latest"`, full default select.** Returns one obs per place per facet — small (~21 MB measured) and parseable (reduced `select` breaks the lib's typed model — verified, so do NOT use it). Coverage at `latest` == coverage over `all` (a facet covers P at latest iff it has any data for P), so the place-coverage primary is faithful; only the obs-count tiebreaker is lost.

**3. Extract the ranking into a shared helper.** Pull the stats-gather + `max(...)` (169-211) into `rank_primary_facet(variable_data: ByVariable, date_filter) -> str | None`. The probe calls it on the `latest` response; `_process_sources_and_filter_observations` calls it on the full response. One implementation, no drift.

**4. Scope: `child_place_type` AND `date="all"` AND no `source_override`.** Single-place (no fan-out, tiny), explicit override (facet known), and `latest`/single-date (already tiny) skip the probe. Date RANGES are excluded for now: the `latest` probe's coverage can mismatch a range-filtered ranking (a facet whose latest obs falls outside the range would be miscounted). Ranges keep current behavior; users can pass `source_override`. (Open for Gate 1: whether to extend to ranges via a range-scoped probe later.)

**5. Raise `DC_MAX_PLACES` default 1000 → 5000.** Memory dropped ~10×, so county-scale (~3,238) is now safe (~148 MB). 5000 places × 1 var = 5000 series, far under the ~tens-of-thousands series cap. The guardrail's purpose shifts from memory→series-cap; A-ii (sharding) removes it entirely for beyond-cap geographies.

## Risks / Trade-offs

- **Coverage-tie fidelity (the one accepted behavior change).** When sources tie on place-coverage, the probe lacks obs-count, so the tiebreak falls to latest-date/facet-order → may pick a different (equally-covering) source than today. Documented; `source_override` is exact. Perfect parity needs the full multi-facet pull (the thing we avoid).
- **Two API calls** for the auto case (probe + filtered). Probe is cheap; the filtered main call is ~10× smaller, so net memory win and usually net time win vs one full call.
- **A-i does NOT bypass the series cap.** The `latest` probe itself fans out all places → it 500s for tract-scale just like the full query. So A-i helps only within the cap (county/state). Beyond-cap = A-ii (shard the places, incl. the probe). The C guardrail still protects the boundary.
- **Dead pagination code** (`fetch_obs_page` page_token, `_extract_next_token`, the token in `get_observations_paginated`) is confirmed inert on v2. Leave it for A-ii (which rewrites the fetch path) rather than churn it here — note only.

## Migration Plan

1. `services/observations.py`: extract `rank_primary_facet(...)` from `_process_sources_and_filter_observations`; have that function call it. Add an auto-select step in `get_observations_paginated` (and `get_observations` if it shares the path) — when scoped, probe (`date="latest"` request → `fetch_obs_page` → `rank_primary_facet`) and set the effective source to `[primary]` (request `source_ids` + route through the override processing path).
2. `config.py`: `DC_MAX_PLACES` default → 5000.
3. Tests (unit, service-level with mocked client returning multi-facet `latest` + filtered full responses) + `docs/reference.md`.
4. Gate: ruff + mypy + full suite + coverage ≥ 80.

**Rollback:** revert; no data migration. The one durable behavior note is the coverage-tie tiebreak — call it out in the PR + docs.
