[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/cfdude-datacommons-mcp-badge.png)](https://mseep.ai/app/cfdude-datacommons-mcp)

# Data Commons MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that exposes the
[Data Commons](https://datacommons.org) public statistical knowledge graph to AI clients such
as Claude Desktop, Claude Code, and ChatGPT.

Data Commons is an open knowledge repository that unifies thousands of public datasets
(census, health, economics, climate, and more) behind a single graph. This server lets an
MCP-enabled client discover the right statistical variables and places, then fetch the actual
observations — automatically exporting large results to CSV in **bounded memory**, even for very
large geographies (e.g. *all US census tracts*), so they stay usable in other tools.

> This is [`cfdude/datacommons-mcp`](https://github.com/cfdude/datacommons-mcp), a
> heavily-redesigned downstream fork. It builds on Google's Data Commons and originated from the
> [Data Commons agent-toolkit](https://github.com/datacommonsorg/agent-toolkit), but this fork is
> **not** published to PyPI and is documented independently here. Server version **1.4.0**.

## The two tools

This server exposes exactly two tools:

| Tool | What it does |
| --- | --- |
| **`search_indicators`** | Finds statistical variables and topics (and which places actually have data for them). **Call this first** to discover valid variable + place DCIDs. |
| **`get_observations`** | Fetches the actual statistical data for a variable + place(s). Small results come back inline; large results export to a CSV/JSON file (with a data preview), and very large geographies are handled in bounded memory via place-sharding. |

The typical flow: `search_indicators` to find DCIDs → `get_observations` to pull the numbers.
See the [reference](docs/reference.md) for the structured shapes each tool returns and example prompts.

## Choose your client

Pick the guide that matches how you'll run the server:

| Client | What it is | Install model | Guide |
| --- | --- | --- | --- |
| **Claude Desktop** | The desktop app (macOS + Windows) | A one-click `.mcpb` extension; configure the API key in the UI | [docs/claude-desktop.md](docs/claude-desktop.md) |
| **Claude Code** | The CLI / coding agent | Register the MCP server yourself from git or a local clone; configure via env vars | [docs/claude-code.md](docs/claude-code.md) |
| **ChatGPT** | OpenAI's app (beta, plan-gated) | A remote HTTPS MCP endpoint via Developer mode | [docs/chatgpt.md](docs/chatgpt.md) |

Reference material that applies to every client lives in [docs/reference.md](docs/reference.md).
Maintainers building the extension itself want [docs/building-the-extension.md](docs/building-the-extension.md).

## Get an API key

Every client needs a Data Commons API key.

1. Create one at [apikeys.datacommons.org](https://apikeys.datacommons.org/) (the key authorizes
   requests to `api.datacommons.org`).
2. Provide it to the server as `DC_API_KEY` — either in the Claude Desktop extension UI, or as an
   environment variable for Claude Code / HTTP serving.

## How output works

`get_observations` decides between two output modes based on result size:

- **Screen (inline).** Small results are returned directly in the response (`output_mode: "screen"`).
- **File (export).** Large results are written to a file on disk (`output_mode: "file"`). Instead of
  the raw rows, the response carries `file_path`, `rows_written`, `file_size_bytes`,
  `unique_places_count`, `format`, plus a **`preview`** (the first rows, so the assistant can see the
  content without opening the file), a **`summary`**, `variable_name`, and `columns`.

The cutover is controlled by `DC_SCREEN_ROW_THRESHOLD` (default **500** rows). Exports default to
**CSV** (`DC_OUTPUT_FORMAT`), so results drop straight into spreadsheets and data tools.

### Large & very large datasets (memory-bounded)

The Data Commons API can't stream or paginate and rejects oversized requests, so the server keeps
big exports memory-bounded in two automatic layers — no extra flags:

- **Source auto-selection.** A large child-place export (e.g. *all US counties × all years*) is
  fetched as a single primary source per place (auto-selected), cutting peak memory ~10× (≈1 GB →
  ≈150 MB) with the same result. Pass an explicit source for exact control.
- **Place-sharding.** A query spanning more places than `DC_SHARD_SIZE` (e.g. *all US census
  tracts*, ~97k) is exported by sharding the place list into batches, writing each to one CSV in
  roughly one-shard memory. The largest exports take a few minutes; batches that hit the API's size
  limits are split and retried automatically. Only queries above the `DC_MAX_PLACES` ceiling are
  refused.
- **Coverage signal.** If the chosen source doesn't cover every place (possible for
  regionally-sourced variables), the result's `places_missing` reports how many.

### Data lineage

CSV exports include data-lineage header rows describing the source and provenance of each series.
Toggle with `DC_INCLUDE_LINEAGE` (default **true**).

### Multi-file export

Setting `DC_MULTI_FILE_EXPORT=true` (or passing `multi_file: true` to a single call) writes
companion metadata files alongside the main export. Off by default.

## Configuration (environment variables)

| Variable | Default | Description |
| --- | --- | --- |
| `DC_API_KEY` | *(required)* | Data Commons API key from [apikeys.datacommons.org](https://apikeys.datacommons.org/). |
| `DC_STORAGE_DIR` | `~/Documents/datacommons-data` | Directory where exported files are written. |
| `DC_OUTPUT_FORMAT` | `csv` | Export format: `csv` or `json`. |
| `DC_SCREEN_ROW_THRESHOLD` | `500` | Max rows returned inline; larger responses export to a file. |
| `DC_MAX_PLACES` | `150000` | Absolute ceiling on child places per query; above it, the query is refused. |
| `DC_SHARD_SIZE` | `15000` | Child-place queries larger than this are exported by sharding into batches. |
| `DC_INCLUDE_LINEAGE` | `true` | Include data-lineage headers in CSV exports. |
| `DC_MULTI_FILE_EXPORT` | `false` | Write companion metadata files alongside exports. |
| `DC_TYPE` | `base` | `base` (datacommons.org) or `custom` (a Custom Data Commons instance). |

Custom Data Commons instances add `CUSTOM_DC_URL`, `DC_SEARCH_SCOPE`, `DC_BASE_INDEX`, and
`DC_CUSTOM_INDEX` — see [Custom Data Commons](docs/reference.md#custom-data-commons) in the reference.

## Documentation map

- [Claude Desktop guide](docs/claude-desktop.md) — install the `.mcpb` extension
- [Claude Code guide](docs/claude-code.md) — register the server from git/local
- [ChatGPT guide](docs/chatgpt.md) — remote HTTPS endpoint (beta)
- [Reference](docs/reference.md) — concepts, tool shapes, env vars, custom DC, MCP Inspector
- [Building the extension](docs/building-the-extension.md) — maintainer doc

## License & credit

Apache-2.0. Builds on Google's [Data Commons](https://datacommons.org) and originated from the
[agent-toolkit](https://github.com/datacommonsorg/agent-toolkit). Data is provided by Data Commons
and its underlying sources; this server does not modify or vouch for the underlying data. Issues
and support: [github.com/cfdude/datacommons-mcp](https://github.com/cfdude/datacommons-mcp).
