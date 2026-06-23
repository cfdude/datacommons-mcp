# Claude Desktop

Claude Desktop is the Anthropic desktop app. The easiest way to add this server is the
**`.mcpb` extension** — a single file you install through the app's UI, with the API key entered
in a form (no terminal, no JSON editing).

Works on **macOS and Windows** (both verified on version 1.3.1).

## Prerequisite: install `uv`

The extension does **not** ship a prebuilt Python environment. It ships its dependency spec
(`pyproject.toml` + `uv.lock`) and uses [`uv`](https://docs.astral.sh/uv/) to build the Python
environment on **first launch**. You must have `uv` installed first.

Install it from the [official instructions](https://docs.astral.sh/uv/getting-started/installation/),
e.g. on macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, follow the PowerShell installer on the same page. If your organization deploys `uv`
centrally, that works too — the extension searches the common install locations.

## Install the extension

1. Get `datacommons-mcp.mcpb` (a maintainer builds it with `build-extension.sh` — see
   [Building the extension](building-the-extension.md)).
2. In Claude Desktop, open **Settings → Extensions → Install from file** and select
   `datacommons-mcp.mcpb`.
3. In the extension's configuration form, fill in:
   - **DataCommons API Key** *(required)* — get one at
     [apikeys.datacommons.org](https://apikeys.datacommons.org/).
   - **Storage Directory** *(optional)* — where exported files are written. Defaults to
     `~/Documents/datacommons-data`.
   - **Screen Row Threshold** *(optional)* — rows returned inline before results export to a file.
     Default `500`.
4. Enable the extension.

## First launch

The **first time** the server starts, `uv` resolves and builds the locked dependency environment
against your Python. This needs **network access once** and may take a minute. After that the
environment is cached and subsequent launches are fast and offline-capable.

## Try it

Once enabled, ask Claude things like:

- "What was the population of California in 2020?"
- "Compare unemployment rates across US states for the last 5 years."
- "Get CO2 emissions for every county in Texas." *(large result — exports to CSV automatically)*

Claude calls `search_indicators` first to find the right variable and place DCIDs, then
`get_observations` to fetch the data. Large pulls are written to your storage directory as CSV;
Claude will tell you the file path. See the [reference](reference.md) for more example prompts.

## Troubleshooting

**"`uv` was not found."**
The extension couldn't locate `uv`. Install it (see above) and restart Claude Desktop. On macOS
the GUI launches with a minimal `PATH`, so the launcher checks `~/.local/bin/uv`,
`/opt/homebrew/bin/uv`, and `/usr/local/bin/uv` by absolute path — make sure `uv` is in one of
those (the standard installer uses `~/.local/bin`).

**First launch hangs or errors about downloading.**
First launch needs network access to resolve and build dependencies. Check your connection /
proxy, then restart. Once the environment is cached, network is no longer required to start.

**Check the logs (macOS).**
Claude Desktop writes per-server MCP logs to:

```
~/Library/Logs/Claude/mcp*.log
```

Open the most recent `mcp-server-datacommons-mcp*.log` to see startup output, the resolved `uv`
path, and any dependency-build errors.

**Exports don't appear.**
Confirm the **Storage Directory** in the extension config (default `~/Documents/datacommons-data`)
and that small queries return inline — only results above the **Screen Row Threshold** export to a
file.
