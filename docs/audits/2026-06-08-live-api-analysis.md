# Live API Analysis — Data Commons (2026-06-08)

**Purpose:** Satisfy the global CLAUDE.md prerequisite — *before writing any spec that persists external-API data, verify the API from the source with a live call dumping the full field set, and let the real payload shape the data model.* This MCP server wraps the Data Commons API and persists observation data to CSV, so this analysis precedes the OpenSpec proposals (especially `modularize-core`, which touches the data models).

**Method:** Live production calls (HTTP 200) against every upstream endpoint the two tools use, using the repo's own client defaults (`search_indices=['base_uae_mem']`, `sv_search_base_url=https://datacommons.org`, `x-surface: mcp-1.2.2`). Full raw payloads saved under `docs/audits/api-samples/*.json` as contract fixtures.

---

## Endpoints in use

| Tool | Endpoint | Shape |
|------|----------|-------|
| `search_indicators` | `GET datacommons.org/api/nl/search-indicators` | params `queries[]`, `limit_per_index`, `index[]`; header `x-surface` |
| `get_observations` | `POST api.datacommons.org/v2/observation` (via `datacommons-client`) | `select`, `entity`, `variable`, `date` |
| place resolution | `POST api.datacommons.org/v2/resolve` | `nodes[]`, `property:"<-description->dcid"` |
| names / types | `POST api.datacommons.org/v2/node` | `nodes[]`, `property:"->[name,typeOf]"` |

> The legacy `/api/nl/search-vector` endpoint is still in the code behind `use_search_indicators_endpoint` (default **True**) with `TODO: remove once new endpoint is live` markers — a migration that should be completed (drop the dead legacy path).

---

## Full field sets (live, 2026-06-08)

### `search-indicators` → `search-indicators.json`
```
queryResults[].{ query, indexResults[].{ index, defaultThreshold, results[] } }
responseMetadata.{ thresholdOverride }
results[] item: { dcid, name, description, typeOf, score, search_descriptions[] }
```

### `v2/observation` → `v2-observation.json`
```
byVariable.{var}.byEntity.{entity}.orderedFacets[].{ facetId, observations[].{date,value}, obsCount, earliestDate, latestDate }
facets.{facetId}.{ importName, measurementMethod, observationPeriod, provenanceUrl }
```

### `v2/resolve` → `v2-resolve.json`
```
entities[].{ node, candidates[].{ dcid } }
```

### `v2/node` → `v2-node.json`
```
data.{dcid}.arcs.{ name, typeOf }.nodes[].{ value | dcid }
```

---

## Code coverage: what we capture vs. what's available

| Field(s) | Available | Captured by code? | Note |
|----------|-----------|-------------------|------|
| search: `dcid, name, description, typeOf, score, search_descriptions` | ✅ | ✅ (`clients.py` transform → `SearchIndicator`) | Good coverage. |
| search: `defaultThreshold`, `responseMetadata.thresholdOverride` | ✅ | ❌ **0 refs** | **Opportunity:** the API now returns a per-index relevance threshold + override; we don't use it. Could filter low-`score` matches instead of relying solely on `limit_per_index`. |
| obs: facet lineage `importName, measurementMethod, observationPeriod, provenanceUrl` | ✅ | ✅ via `FacetMetadata` aliases (`observations.py:270-277`) | Flows through the `datacommons-client` library's `Observation`/`OrderedFacet` types. |
| obs: `obsCount, earliestDate, latestDate` per ordered facet | ✅ | partial | Useful summary metadata for large-export decisions; verify it's surfaced. |

---

## Drift & silent-failure risks (the reason for this analysis)

1. **Observation model depends on the `datacommons-client` library, not the raw API.** Our code has **zero** raw-JSON references for observations; it imports `Observation`/`OrderedFacet` from `datacommons_client.models.observation` and maps lineage via Pydantic **aliases with `default=None`**. If the API or library renames a facet field, our lineage columns silently become blank — no error. **Mitigation for the spec:** (a) pin `datacommons-client` to a bounded version; (b) add a **contract test** asserting the saved `v2-observation.json` sample still populates `import_name`/`measurement_method`/`provenance_url`; refresh the sample on dependency bumps.
2. **Search endpoint mid-migration.** `search-vector` (legacy) vs `search-indicators` (current) both exist in code. The spec should complete the migration and delete the legacy path + its `place-like` constraint scaffolding (`TODO(@jm-rivera)` markers).
3. **Unused relevance signal.** `defaultThreshold`/`thresholdOverride` are returned but ignored — the search spec should decide whether to adopt score-threshold filtering (better precision than a raw count cap).

---

## Recommendations for the specs

- **Capture, don't expand:** the data the server genuinely needs is `{dcid, name, typeOf, score}` (+ `description`/`search_descriptions` for display/ranking) for search, and `{date, value}` + facet `{importName, measurementMethod, observationPeriod, provenanceUrl}` for observations/lineage. Everything else (threshold internals, arc plumbing) can stay un-modeled.
- **Pin `datacommons-client`** with bounds (currently unbounded — see forensic review) and treat its observation models as the contract; add a fixture-backed contract test.
- **Adopt score-thresholding** in the search service (use `defaultThreshold`) — flagged for the `modularize-core` search split.
- **Complete the search-vector → search-indicators migration**; delete the legacy path.
- Re-run this probe (`/tmp/dc_api_probe.py` pattern) whenever bumping `datacommons-client` or `fastmcp`, and before the `modularize-core` spec is applied.

*Raw samples: `docs/audits/api-samples/{search-indicators,v2-observation,v2-resolve,v2-node}.json`.*
