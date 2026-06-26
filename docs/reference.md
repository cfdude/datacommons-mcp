# Reference

Concepts, tool shapes, configuration, and tooling that apply to every client. For install steps,
see the [Claude Desktop](claude-desktop.md), [Claude Code](claude-code.md), or
[ChatGPT](chatgpt.md) guides.

## Concepts

**Data Commons** unifies thousands of public datasets behind a single knowledge graph. You query it
in terms of:

- **Variables** — statistical measures (e.g. *Population*, *Unemployment Rate*, *CO2 Emissions*),
  each identified by a **DCID** (Data Commons ID).
- **Topics** — categories that group related variables (e.g. *Health → Clinical Data*).
- **Places** — geographic entities arranged in a containment hierarchy
  (*World → Country → State → County*), also identified by DCIDs.

The same concept can use **different variable DCIDs for different place types** (a country-level
*Population* variable may differ from a state-level one). That's why you discover DCIDs with
`search_indicators` before fetching data — never guess them.

## The two tools

### `search_indicators` — discover DCIDs first

Finds candidate variables and topics for a query, and (when you pass places) which places actually
have data. **Call this before `get_observations`.**

Returns a typed `SearchResponse`:

| Field | Shape | Meaning |
| --- | --- | --- |
| `variables` | list of variable objects | Matching variables; each carries `dcid` and `places_with_data`. |
| `topics` | list of topic objects (browse mode) | Matching topics with their member variables/topics. |
| `dcid_name_mappings` | `{dcid: name}` | Human-readable names for the DCIDs in the response. |
| `dcid_place_type_mappings` | `{place_dcid: [types]}` | Place type(s) for each place DCID (used to pick a `child_place_type`). |
| `status` | string | Operation status (e.g. `SUCCESS`). |

Each indicator carries **`places_with_data`** — the place DCIDs that actually have observations for
it. Use that to confirm a variable + place combination before fetching.

**Example prompts that trigger it:**

- "Find indicators for carbon emissions."
- "Which places have data on unemployment rate?"
- "What population variables exist for US counties?"

### `get_observations` — fetch the data

Fetches actual observations for a variable + place(s). Returns a discriminated union keyed on
`output_mode`:

**Screen (small results, inline):**

| Field | Meaning |
| --- | --- |
| `output_mode` | `"screen"` |
| `data` | The observation data, returned inline. |

**File (large/paginated results, written to disk):**

| Field | Meaning |
| --- | --- |
| `output_mode` | `"file"` |
| `file_path` | Path to the written export file (server-local). |
| `rows_written` | Total observation rows written. |
| `pages_fetched` | API pages fetched during export. |
| `file_size_bytes` | Size of the written file. |
| `unique_places_count` | Distinct places in the export. |
| `format` | `"csv"` or `"json"`. |
| `preview` | A bounded sample (first ~10 rows) of the export, so the assistant can see the content without opening the file. |
| `columns` | The column headers of the export. |
| `variable_name` | Display name of the variable. |
| `summary` | One-line summary: total rows written + the file path. |

> The full dataset always goes to the file; `preview` is only a small sample so the model can confirm and reason about the result inline.

**Example prompts that trigger it:**

- "Get the population of California in 2020."
- "Show CO2 emissions for all counties in Texas." *(large → file export)*
- "Compare GDP for the US, China, and India over the last decade."

> There is no third tool. `search_indicators` and `get_observations` are the complete surface.

## Output: screen vs. file

`get_observations` chooses its mode by result size:

- **Inline (`screen`)** when the result is at or below `DC_SCREEN_ROW_THRESHOLD` (default **500**
  rows) — the data comes back in the response.
- **File (`file`)** when the result is larger or paginated — rows stream to a file under the storage
  directory, and the response carries the export metadata above instead of raw rows.

Exports default to **CSV** (`DC_OUTPUT_FORMAT`), so results are immediately usable in spreadsheets
and other tools. CSV exports include **data-lineage header rows** describing source and provenance
(toggle with `DC_INCLUDE_LINEAGE`, default true). Setting `DC_MULTI_FILE_EXPORT=true` writes
companion metadata files alongside the main export.

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `DC_API_KEY` | *(required)* | Data Commons API key from [apikeys.datacommons.org](https://apikeys.datacommons.org/). |
| `DC_STORAGE_DIR` | `~/Documents/datacommons-data` | Directory where exported files are written. |
| `DC_OUTPUT_FORMAT` | `csv` | Export format: `csv` or `json`. |
| `DC_SCREEN_ROW_THRESHOLD` | `500` | Max rows returned inline; larger responses export to a file. |
| `DC_MAX_PLACES` | `1000` | Max child places a single `get_observations` query may span before it is refused (see below). |
| `DC_MAX_PAGES` | `100` | Max API pages fetched per paginated request. |
| `DC_INCLUDE_LINEAGE` | `true` | Include data-lineage headers in CSV exports. |
| `DC_MULTI_FILE_EXPORT` | `false` | Write companion metadata files alongside exports. |
| `DC_TYPE` | `base` | `base` (datacommons.org) or `custom` (a Custom Data Commons instance). |

> **Very large queries.** `get_observations` builds the full result in server memory before
> writing, so a query spanning a huge geography (e.g. *all US counties × all years*) can use
> a lot of RAM. As a safeguard, a `child_place_type` query spanning more than `DC_MAX_PLACES`
> child places is **refused** with guidance to narrow it (a specific date/range, a coarser
> place type, or fewer places). Raise `DC_MAX_PLACES` on a high-memory machine, or lower it to
> be cautious. (This is a stopgap; streaming support for large exports is planned.)

### Custom Data Commons

A [Custom Data Commons](https://docs.datacommons.org/custom_dc/) instance hosts your own data
alongside the base graph. To target one, set `DC_TYPE=custom` and:

| Variable | Description |
| --- | --- |
| `CUSTOM_DC_URL` | Base URL of your custom Data Commons instance *(required for custom)*. |
| `DC_SEARCH_SCOPE` | What to search — base graph, your custom data, or both. |
| `DC_BASE_INDEX` | Search index used for the base graph. |
| `DC_CUSTOM_INDEX` | Search index used for your custom data. |

## CLI

The `datacommons-mcp` entry point has one command group, `serve`, with two transports:

```bash
datacommons-mcp serve stdio [--verbose] [--storage-dir PATH]
datacommons-mcp serve http  [--host localhost] [--port 8080] [--verbose] [--storage-dir PATH]
```

- **`serve stdio`** — for local MCP clients (Claude Desktop, Claude Code).
- **`serve http`** — Streamable HTTP at `http://<host>:<port>/mcp` (default
  `http://localhost:8080/mcp`); used for remote clients such as ChatGPT.

`--storage-dir` overrides `DC_STORAGE_DIR` for that run.

## MCP Inspector

To poke at the tools directly, use the
[MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector \
  uvx --from git+https://github.com/cfdude/datacommons-mcp datacommons-mcp serve stdio
```

Set `DC_API_KEY` in your environment first. The Inspector opens a UI where you can call
`search_indicators` and `get_observations` and inspect their structured responses.

## Data disclaimer

All data comes from [Data Commons](https://datacommons.org) and its underlying public sources. This
server retrieves and formats that data; it does not modify, validate, or vouch for the underlying
values. Check Data Commons for source attribution and methodology.
