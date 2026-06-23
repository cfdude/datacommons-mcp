# Claude Code

Claude Code is the Anthropic CLI / coding agent. There is **no extension** — you register the MCP
server yourself and configure it with environment variables.

## Critical: run *this* fork, not the PyPI package

`uvx datacommons-mcp` installs the **upstream** package (v1.2.1) from PyPI — **not** this fork.
This fork is intentionally **not** published to PyPI. To run this fork you must point `uv` at the
git repo or a local clone:

**From git:**

```bash
uvx --from git+https://github.com/cfdude/datacommons-mcp datacommons-mcp serve stdio
```

**From a local clone:**

```bash
git clone https://github.com/cfdude/datacommons-mcp
cd datacommons-mcp
uv run datacommons-mcp serve stdio
# or, from anywhere:
uvx --from /path/to/datacommons-mcp datacommons-mcp serve stdio
```

You need [`uv`](https://docs.astral.sh/uv/) installed either way.

## Register with `claude mcp add`

Point the command at one of the invocations above and pass the API key via `--env`:

```bash
claude mcp add datacommons \
  --env DC_API_KEY=your-api-key-here \
  -- uvx --from git+https://github.com/cfdude/datacommons-mcp datacommons-mcp serve stdio
```

## Register with `.mcp.json`

Equivalently, add an `mcpServers` block to a project `.mcp.json` (or your Claude Code settings).
Git form:

```json
{
  "mcpServers": {
    "datacommons": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/cfdude/datacommons-mcp",
        "datacommons-mcp",
        "serve",
        "stdio"
      ],
      "env": {
        "DC_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

Local-clone form (swap the `--from` target for a path, or use `uv run`):

```json
{
  "mcpServers": {
    "datacommons": {
      "command": "uvx",
      "args": ["--from", "/path/to/datacommons-mcp", "datacommons-mcp", "serve", "stdio"],
      "env": {
        "DC_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## Configuration

All configuration is via environment variables in the `env` block (there is no UI). Get an API key
at [apikeys.datacommons.org](https://apikeys.datacommons.org/). Common settings:

| Variable | Default | Description |
| --- | --- | --- |
| `DC_API_KEY` | *(required)* | Data Commons API key. |
| `DC_STORAGE_DIR` | `~/Documents/datacommons-data` | Where exported files are written. |
| `DC_OUTPUT_FORMAT` | `csv` | Export format: `csv` or `json`. |
| `DC_SCREEN_ROW_THRESHOLD` | `500` | Max rows returned inline before results export to a file. |

See the [reference](reference.md#environment-variables) for the full list, including Custom Data
Commons settings.

The `serve stdio` command also accepts `--verbose` (debug logging) and
`--storage-dir <path>` (overrides `DC_STORAGE_DIR`).

## Remote (HTTP) option

If you'd rather run the server as a long-lived HTTP service and connect Claude Code to it, start:

```bash
datacommons-mcp serve http --host localhost --port 8080
```

This serves a Streamable HTTP endpoint at `http://localhost:8080/mcp`. Set `DC_API_KEY` in that
process's environment. Flags: `--host` (default `localhost`), `--port` (default `8080`),
`--verbose`, `--storage-dir`. This same HTTP mode is what ChatGPT requires — see the
[ChatGPT guide](chatgpt.md).
