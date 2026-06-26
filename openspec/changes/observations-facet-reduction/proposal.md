## Why

`get_observations` peaks at ~1 GB RSS for an all-US-counties × all-years export (4 MB file). Investigation ([[observations-streaming-reality]]) found the v2 API **cannot stream or paginate** (confirmed against the v2 REST + Python docs — no page token exists; oversized queries are hard-rejected with HTTP 500), so the queued "true streaming via pagination" design is impossible. But the cost is almost entirely **duplicate source-facets**: the raw response is ~11× the written rows (county query: 532,944 raw obs → 48,303 written) because the service pulls **every** source then filters to **one** primary source per place.

The service already collapses to a single global primary source and **drops places that don't have it** (`_process_sources_and_filter_observations`, services/observations.py:199-232). So asking the API for **only that facet** (`filter_facet_ids`, already plumbed via `source_override → source_ids`) yields the **same output** at ~10× less memory. Measured end-to-end via `get_observations(..., source_override=<primary>)`: **148 MB RSS / 45 MB heap** vs the ~1 GB / 456 MB baseline. This makes county/state-scale exports feasible **without streaming** — item A-i. (Beyond the API's series cap — tract-scale — needs place-sharding, the separate `observations-place-sharding` epic, A-ii.)

## What Changes

- **Auto-select the primary facet for big child-place queries, then fetch only that facet — reconstructing the full output from the probe.** For a `child_place_type` query with `date="all"` (and no `date` range/single-date) and no explicit `source_override`:
  1. **Cheap probe:** fetch the same query at `date="latest"` (one obs per place per facet — small), rank facets with the existing ranking logic, pick the primary facet id. **Keep** the probe's per-facet coverage + full place set (don't discard it).
  2. **Filtered fetch:** re-query with the original date but `source_ids=[primary]` → the API returns only that facet (~10× smaller). NOTE (verified live): `filter_facet_ids` returns ONLY places that HAVE the primary facet — e.g. 3,232 of 3,237 counties — so the filtered fetch alone DROPS the places lacking it.
  3. **Reconstruct faithful output:** today's non-reduced path re-adds *every* place (incl. those lacking the primary) with an empty time-series, and reports per-source `alternative_sources`. Rebuild BOTH from the kept probe: add empty-series `PlaceObservation`s for probe places missing from the filtered result, and populate `alternative_source_counts` from the probe's per-source coverage. Output is then identical to today (same place set, same primary obs, same alternative-source metadata) except the documented coverage-tie tiebreak.
- **Refactor** the facet-ranking out of `_process_sources_and_filter_observations` into a reusable helper (`ByVariable → (primary facet id, per-source coverage counts)`) used by both the probe and the existing full path (no duplicated ranking).
- **Raise `DC_MAX_PLACES`** default (the C guardrail) from 1000 → a higher value (e.g. 5000) now that per-query memory dropped ~10×, so county-scale (~3,238 places) exports are **allowed** — calibrated to stay well under the API series cap. The guardrail's role shifts from "memory protection" to "stay under the API's hard series cap" (fully handled by A-ii sharding later).

**CLIENT-VISIBLE changes (intended):**
- Large child-place `date="all"` exports use far less server memory and county-scale queries that C used to refuse now succeed.
- **Source-selection fidelity (the one documented tradeoff):** the cheap `latest` probe cannot see total-observation-count (the 2nd tiebreaker), so when two sources **tie on place-coverage**, the auto-selected primary may differ from today's full-data ranking (it falls through to latest-date/facet-order instead). Narrow; only affects coverage-ties. Perfect parity is impossible without the full multi-facet pull (the very thing we avoid). `source_override` (explicit) is always exact. (Place set + primary obs + `alternative_sources` are reconstructed faithfully from the probe — see step 3 — so those do NOT change.)
- **Memory caveat (C4):** raising `DC_MAX_PLACES` to 5000 also permits UNREDUCED child queries — a single date or an explicit date RANGE both run at `date=ALL` server-side and are NOT facet-reduced (the `latest` probe can't faithfully rank a range) — at up to 5× the place count. A single date is still tiny (one obs/place), but a WIDE date range over thousands of places stays memory-heavy until place-sharding (A-ii). Documented limitation.

Non-goals: NO streaming/pagination (impossible on v2); NO place-sharding / beyond-series-cap support (that's A-ii); NO change to single-place, explicit-`source_override`, `date="latest"`, single-date, or date-range queries (date ranges keep current behavior — the `latest` probe's coverage may not match a range-filtered ranking; use `source_override` for exact-source range exports).

## Capabilities

### New Capabilities
- `observations-facet-reduction`: `get_observations` auto-selects the primary source for large child-place exports and requests only that facet from the API, cutting peak server memory ~10× (so county/state-scale exports succeed) without changing the result, except for a documented narrow source-tiebreak difference.

## Impact

- **Code:** `services/observations.py` (extract ranking helper; auto-facet-select for `child_place_type` + `date="all"` + no override; set `source_ids=[primary]`); `config.py` (`DC_MAX_PLACES` default ↑); possibly a thin client probe wrapper (or reuse `fetch_obs`).
- **Tests:** ranking-helper unit tests; auto-select picks the coverage-primary; the filtered fetch requests `filter_facet_ids=[primary]`; single-place / override / `latest` / range queries unchanged; the raised `DC_MAX_PLACES` lets county-scale through; coverage-tie behavior pinned.
- **Docs:** `docs/reference.md` — note auto source-selection + the memory profile + the new `DC_MAX_PLACES` default + the tie caveat.
- **Risk:** MEDIUM. Two API calls for the auto case (probe is cheap; net memory + usually net time win). The documented source-tiebreak change in coverage-ties. The series cap still applies (A-i does not bypass it; the probe itself fans out all places, so tract-scale still 500s → A-ii).
