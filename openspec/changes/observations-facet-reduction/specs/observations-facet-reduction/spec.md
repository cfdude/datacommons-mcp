## ADDED Requirements

### Requirement: Large child-place exports auto-reduce to the primary facet
For a `child_place_type` query at `date="all"` (with no date range/single-date and no `source_override`), the paginated observations path (`get_observations_paginated`, used by the `get_observations` tool) SHALL determine the primary source via a cheap probe and request only that facet, to cut server memory.

#### Scenario: Auto facet-reduction on a big child-place query
- **WHEN** the paginated path runs a `child_place_type`, `date="all"` query with no `source_override`
- **THEN** it first fetches the same query at `date="latest"` to rank facets and pick the primary facet id, then re-queries the full date range with `source_ids=[primary]` so the API returns only that facet

#### Scenario: The filtered fetch actually restricts the facet server-side
- **WHEN** the second (filtered) fetch is issued
- **THEN** it passes `filter_facet_ids=[primary]` to the API (via `source_ids`), so the raw response holds one facet, not all sources

### Requirement: Reduced output is faithful to the non-reduced output
Because `filter_facet_ids` returns only places that have the primary facet (verified), the reduced path SHALL reconstruct the full output from the kept probe so it matches today.

#### Scenario: Places lacking the primary source are preserved as empty-series
- **WHEN** some places have data only from non-primary sources (so the filtered fetch omits them)
- **THEN** those places still appear in the result with an empty time-series — the same place set as the non-reduced path — reconstructed from the `latest` probe

#### Scenario: alternative_sources is preserved
- **WHEN** the reduced path builds the result
- **THEN** `alternative_sources` is populated from the probe's per-source coverage (the same metadata the non-reduced path reports), not left empty

### Requirement: Auto-reduction is correctly scoped
Auto facet-reduction SHALL apply only where it is safe and beneficial, leaving other queries unchanged.

#### Scenario: Single-place queries are unchanged
- **WHEN** `get_observations` is called without `child_place_type`
- **THEN** no probe runs and behavior is exactly as before

#### Scenario: Explicit source_override is unchanged
- **WHEN** `source_override` is provided
- **THEN** no probe runs (the facet is already known) and the existing override path is used

#### Scenario: latest / single-date and date-range queries are unchanged
- **WHEN** the query is `date="latest"`, a single date, or an explicit date range
- **THEN** no auto-reduction probe runs (these either have no memory problem or the `latest` probe's coverage may not match a range-filtered ranking) and behavior is as before

#### Scenario: The gate distinguishes true date="all" from single-date/range
- **WHEN** deciding whether to auto-reduce
- **THEN** the gate requires `date_type == ObservationDateType.ALL AND date_filter is None` (since a single date and a range both set `date_type=ALL` with a non-None `date_filter`), so single-date and range queries are correctly excluded

### Requirement: The probe runs only after the size guardrail
The auto-reduction probe SHALL NOT run for a query the size guardrail refuses.

#### Scenario: A beyond-budget query is refused before any probe
- **WHEN** a `child_place_type` `date="all"` query exceeds `DC_MAX_PLACES`
- **THEN** the guardrail raises `ResultTooLargeError` BEFORE the probe, and zero probe fetches are issued (the probe itself fans out all places and would 500 — only place-sharding/A-ii handles beyond-cap)

### Requirement: Facet ranking is shared, not duplicated
The primary-facet ranking SHALL be a single reusable function used by both the probe and the existing full-response path.

#### Scenario: One ranking implementation
- **WHEN** the primary facet is chosen (probe or full path)
- **THEN** both call the same extracted ranking helper over a `ByVariable`, so selection logic cannot drift between the two

### Requirement: Source selection stays faithful except in coverage ties
The auto-selected primary SHALL match today's selection except where the cheap probe cannot disambiguate.

#### Scenario: Primary matches today when coverage differs
- **WHEN** one source covers more places than the others
- **THEN** the auto-selected primary is that source (same as the full-data ranking)

#### Scenario: Coverage tie may differ, and is documented
- **WHEN** two or more sources tie on place-coverage
- **THEN** the probe (which lacks total-observation-count) breaks the tie on latest-date/facet-order, which MAY differ from today's obs-count tiebreak — this is the one accepted, documented behavior change

### Requirement: The place budget reflects the lower memory
`DC_MAX_PLACES` SHALL be raised so county-scale exports are permitted under the new memory profile.

#### Scenario: County-scale child-place query is allowed
- **WHEN** a `child_place_type` query spans ~3,238 places (e.g. US counties) with auto-reduction
- **THEN** it is NOT refused by the size guardrail (the raised `DC_MAX_PLACES` default permits it) and completes within bounded memory

#### Scenario: Beyond the series cap is still refused
- **WHEN** a query spans more places than `DC_MAX_PLACES` (still well under the API's hard series cap)
- **THEN** it is refused by the existing guardrail (A-i does not bypass the API series cap; that is A-ii / place-sharding)

### Requirement: Suite and docs stay green
The change SHALL keep the suite green and document the new behavior.

#### Scenario: Tests pin the new behavior
- **WHEN** the suite runs
- **THEN** unit tests cover the ranking helper, auto-select on a big child-place query, the filtered fetch's `filter_facet_ids`, the unchanged paths, the coverage-tie behavior, and the raised `DC_MAX_PLACES`, and the full non-e2e suite passes
