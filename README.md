# Data Commons MCP Server

This is a Model Context Protocol (MCP) server for fetching public statistical data from [Data Commons](https://datacommons.org) instances.

Data Commons is an open knowledge repository that provides a unified view across multiple public data sets and statistics.  This server allows any MCP-enabled agent or client to query the Data Commons knowledge graph.

## Features
* **MCP-Compliant:** Implements the Model Context Protocol for seamless agent integration.
* **Data Commons Access:** Fetches public statistics and data from the base datacommons.org knowledge graph.
* **Custom Instance Support:** Can be configured to work with Custom Data Commons instances.
* **Flexible Serving:** Runs over both streamable HTTP and stdio.
* **Large Dataset Handling:** Automatic pagination and streaming for large observation queries.
* **Multiple Output Modes:** Choose between screen display, automatic CSV export, or forced file output.
* **Multi-File Export:** Split large exports by place, place type, date, or chunk size.
* **Data Lineage:** CSV exports include comprehensive lineage headers for data provenance.
* **Progress Streaming:** Real-time progress updates via STDIO or SSE transport.

## Quickstart

### Prerequisites

1.  You must have a Data Commons API key; create one at [apikeys.datacommons.org](https://apikeys.datacommons.org/).
2.  Install `uv` by following the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation).

### Configuration

Set the following required environment variable in your shell:

```
export DC_API_KEY=<your API key>
```

### Start the server 

Run the server from your command line in one of two modes:

**Streamable HTTP**

This runs the server with Streamable HTTP.

```bash
# Runs on default port 8080
uvx datacommons-mcp serve http [--port <PORT>]
```

The server will be available at `http://localhost:<port>/mcp`.

**stdio**

This transport mode is intended for local integrations and is programmatically configured within a client (like Gemini CLI settings) to communicate over `stdio`.

```bash
uvx datacommons-mcp serve stdio
```

## Clients

You can use any MCP-enabled agent or client to connect to your running server. For example, see the [Data Commons MCP documentation](https://github.com/datacommonsorg/agent-toolkit/blob/main/docs/user_guide.md) for guides on connecting:
* [Google Gemini CLI](https://github.com/datacommonsorg/agent-toolkit/blob/main/docs/quickstart.md)
* [Google ADK natively](https://github.com/datacommonsorg/agent-toolkit/blob/main/docs/user_guide.md#use-the-sample-agent)
* [Google ADK in Colab](https://colab.research.google.com/github/datacommonsorg/agent-toolkit/blob/main/notebooks/datacommons_mcp_tools_with_custom_agent.ipynb)

Or see your preferred client's documentation for how to configure it, using the commands listed above.

## Advanced Configuration

### Server Options

**HTTP Mode Options**

```bash
uvx datacommons-mcp serve http [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | 8080 | Port to run the HTTP server on |
| `--progress-transport` | stdio | Transport for progress updates (`stdio` or `sse`) |
| `--verbose` | false | Enable verbose progress logging |
| `--sse-port` | 8081 | Port for SSE progress server (when using SSE transport) |
| `--storage-dir` | `./datacommons-data` | Directory for exported data files |

**stdio Mode Options**

```bash
uvx datacommons-mcp serve stdio [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--verbose` | false | Enable verbose progress logging |
| `--storage-dir` | `./datacommons-data` | Directory for exported data files |

### Large Dataset Handling

The server automatically handles large datasets through pagination-based streaming and row count thresholds:

1. **Auto Mode (default):** Automatically detects large datasets and streams them to CSV files. File mode is triggered when:
   - The API returns multiple pages (pagination detected), OR
   - The response exceeds the row threshold (default: 500 rows)
2. **Screen Mode:** Forces all results to screen (use with caution for large datasets).
3. **File Mode:** Forces all results to CSV file, even for small datasets.

The row threshold prevents large single-page responses from flooding the context window. Configure it via `DC_SCREEN_ROW_THRESHOLD` environment variable.

Output files are saved to a configurable storage directory (default: `./datacommons-data`) with timestamped filenames. Configure the storage directory via the `--storage-dir` CLI option or `DC_STORAGE_DIR` environment variable.

### Multi-File Export

For very large datasets, you can split exports into multiple files using different strategies:

| Strategy | Description |
|----------|-------------|
| `by_place` | One file per unique place DCID |
| `by_place_type` | One file per place type (State, County, etc.) |
| `by_date` | One file per year |
| `by_chunk` | Fixed number of rows per file |

Each multi-file export includes a manifest JSON file describing all exported files.

### Data Lineage Headers

CSV exports include comprehensive lineage headers as comments at the top of each file:

```csv
# ============================================================
# Data Commons MCP Server Export
# ============================================================
# Query:
#   variable_dcid: Count_Person
#   variable_name: Total Population
#   place_dcid: country/USA
#   child_place_type: State
# Date Filter:
#   date_filter: range
#   date_range_start: 2019-01-01
#   date_range_end: 2021-12-31
# Source:
#   source_id: CensusACS5YearSurvey
#   source_url: https://data.census.gov
# Export:
#   server_version: 1.2.0
#   timestamp: 2024-01-15T10:30:00Z
#   total_pages: 5
# ============================================================
#
place_dcid,place_name,place_type,variable_dcid,variable_name,date,value,source_id
...
```

To disable lineage headers, set `include_lineage=False` in the configuration.

### Progress Streaming

The server supports real-time progress updates during large data fetches:

**STDIO Transport (default)**
Progress messages are written to stderr in JSON format, suitable for programmatic parsing.

**SSE Transport**
For web-based clients, progress can be streamed via Server-Sent Events:

```bash
uvx datacommons-mcp serve http --progress-transport sse --sse-port 8081
```

Connect to `http://localhost:8081/events` to receive real-time progress updates.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DC_API_KEY` | Yes | Your Data Commons API key |
| `DC_API_ROOT` | No | Custom API root URL |
| `DC_WEBSITE_ROOT` | No | Custom website root URL |
| `DC_STORAGE_DIR` | No | Directory for storing exported data files (default: `./datacommons-data`) |
| `DC_OUTPUT_FORMAT` | No | Default format for file exports: `csv` or `json` (default: `csv`) |
| `DC_MAX_PAGES` | No | Maximum pages to fetch in paginated requests (default: `100`) |
| `DC_INCLUDE_LINEAGE` | No | Include data lineage headers in CSV exports (default: `true`) |
| `DC_MULTI_FILE_EXPORT` | No | Enable multi-file export with companion CSVs (default: `false`) |
| `DC_SCREEN_ROW_THRESHOLD` | No | Max rows to return to screen in auto mode; larger responses go to file (default: `500`) |

### Using MCP Tools with a Custom Data Commons

Follow the [Guide for using MCP Tools with Custom Data Commons](https://github.com/datacommonsorg/agent-toolkit/blob/main/docs/user_guide.md#custom-data-commons) to set additional environment variables required for custom configuration.

## Version History

### v1.2.0
- Added pagination-based streaming for large datasets
- Added automatic CSV export for multi-page responses
- Added output mode selection (auto, screen, file)
- Added transport abstraction layer (STDIO, SSE)
- Added SSE server for real-time progress streaming
- Added multi-file export with split strategies
- Added comprehensive data lineage headers to CSV exports

### v1.1.x
- Initial release with core MCP functionality
- Search indicators and get observations tools
- Custom Data Commons support
