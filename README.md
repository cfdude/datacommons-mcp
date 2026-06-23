# Data Commons MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that exposes the
[Data Commons](https://datacommons.org) public statistical knowledge graph to AI clients such
as Claude Desktop, Claude Code, and ChatGPT.

Data Commons is an open knowledge repository that unifies thousands of public datasets
(census, health, economics, climate, and more) behind a single graph. This server lets an
MCP-enabled client discover the right statistical variables and places, then fetch the actual
observations — automatically streaming large results to CSV so they stay usable in other tools.

> This is [`cfdude/datacommons-mcp`](https://github.com/cfdude/datacommons-mcp), a
> heavily-redesigned downstream fork. It builds on Google's Data Commons and originated from the
> [Data Commons agent-toolkit](https://github.com/datacommonsorg/agent-toolkit), but this fork is
> **not** published to PyPI and is documented independently here. Server version **1.3.1**.

## The two tools

This server exposes exactly two tools:

| Tool | What it does |
| --- | --- |
| **`search_indicators`** | Finds statistical variables and topics (and which places actually have data for them). **Call this first** to discover valid variable + place DCIDs. |
| **`get_observations`** | Fetches the actual statistical data for a variable + place(s). Small results come back inline; large results stream to a CSV/JSON file. |

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
- **File (export).** Large or paginated results stream to a file on disk
  (`output_mode: "file"`), and the response carries `file_path`, `rows_written`, `pages_fetched`,
  `file_size_bytes`, `unique_places_count`, and `format` instead of the raw rows.

The cutover is controlled by `DC_SCREEN_ROW_THRESHOLD` (default **500** rows). Exports default to
**CSV** (`DC_OUTPUT_FORMAT`), so results drop straight into spreadsheets and data tools.

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
| `DC_MAX_PAGES` | `100` | Max API pages fetched per paginated request. |
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
