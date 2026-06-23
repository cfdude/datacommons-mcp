# Building the `.mcpb` extension (maintainers)

This is a maintainer doc for producing the `datacommons-mcp.mcpb` extension that Claude Desktop
users install. End users do **not** need this — point them at the
[Claude Desktop guide](claude-desktop.md).

## The runtime model: uv builds on first launch

The extension does **not** carry a prebuilt Python environment. The bundle ships only the
**dependency spec** (`pyproject.toml` + `uv.lock`), the package **source**, and the **launchers** —
not prebuilt wheels and not a vendored environment. On the user's machine, `uv` resolves and builds
the locked dependencies against their own Python on **first launch** (network needed once, then
cached).

Why this matters:

- It keeps the `.mcpb` small.
- It avoids shipping CPython-minor-version-specific compiled extensions (`.so`) that only load on
  one interpreter — `uv` builds the right wheels for whatever Python the user has (subject to
  `requires-python` in `pyproject.toml`).
- `uv.lock` pins exact versions, so every install is reproducible.

The trade-off: the user must have `uv` installed, and first launch needs network access.

## What `build-extension.sh` assembles

Running `bash build-extension.sh` cleans `build/`, then stages the bundle:

- **`src/datacommons_mcp` → `build/datacommons_mcp`** — the package, copied with `rsync`
  (excluding `__pycache__`, `*.pyc`, `*.pyo`). The bundle is **flattened**: the package sits at the
  bundle root, not under `src/`.
- **`run_server.sh` and `run_server.cmd`** — the macOS/Linux and Windows launchers.
- **`uv.lock`, `README.md`, `LICENSE`** — `uv.lock` pins dependencies; `README.md` and `LICENSE`
  are referenced by `pyproject.toml` and required to build the package.
- **`pyproject.toml`** — copied with a `sed` rewrite of `where = ["src"]` → `where = ["."]`, because
  the bundle is flattened. Without this, `uv`'s editable build on first launch can't find the
  package (setuptools fails resolving the dynamic version attribute).
- **`manifest.json`** — the extension manifest (below).

Then it runs `mcpb pack build/` and renames the output to `datacommons-mcp.mcpb`.

### CI: `--no-pack`

```bash
bash build-extension.sh --no-pack
```

assembles `build/` but skips the `mcpb pack` step (so no `mcpb` CLI is needed). CI uses this to
smoke-test the bundle's first-launch editable build with
`uv run --frozen --project build …`.

## The launchers

Both launchers do the same thing on their platform:

1. Resolve `uv` by **absolute path** first, because Claude Desktop launches from a GUI process with
   a minimal `PATH` that excludes `~/.local/bin` and Homebrew. They check the standalone-installer
   location, then platform package-manager locations, then fall back to a `PATH` lookup:
   - `run_server.sh` (macOS/Linux): `~/.local/bin/uv`, `/opt/homebrew/bin/uv`, `/usr/local/bin/uv`, then `PATH`.
   - `run_server.cmd` (Windows): `%USERPROFILE%\.local\bin\uv.exe`, `%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe`, then `PATH`.
2. If `uv` isn't found, print an actionable error pointing at <https://docs.astral.sh/uv/> and exit non-zero.
3. Exec `uv run --frozen --project "<bundle-dir>" python "<bundle-dir>/datacommons_mcp/run_server.py" "$@"`.
   `--frozen` installs exactly what `uv.lock` pins and never re-resolves.

## `manifest.json`

The manifest selects the launcher per platform:

- Default `mcp_config.command` is `bash` with args `["${__dirname}/run_server.sh"]`.
- `platform_overrides.win32` overrides to `cmd` with args `["/c", "${__dirname}\\run_server.cmd"]`.
- `compatibility.platforms` is `["darwin", "win32"]`.

It exposes the two tools (`search_indicators`, `get_observations`) and three `user_config` fields,
mapped into the launcher environment:

| `user_config` field | Env var | Required | Notes |
| --- | --- | --- | --- |
| `api_key` | `DC_API_KEY` | yes | Sensitive; from [apikeys.datacommons.org](https://apikeys.datacommons.org/). |
| `storage_dir` | `DC_STORAGE_DIR` | no | Defaults to `~/Documents/datacommons-data` when blank. |
| `screen_row_threshold` | `DC_SCREEN_ROW_THRESHOLD` | no | Default `500`. |

> `manifest.json`'s `author`/`homepage`/`documentation`/`support`/`repository` URLs point at
> this fork (`cfdude/datacommons-mcp`). Keep them in sync with the repo if it moves; they are
> metadata only and don't affect the build mechanics described here.

## Dev loop

```
edit source / manifest / launcher
  → bash build-extension.sh
  → reinstall datacommons-mcp.mcpb in Claude Desktop (Settings → Extensions → Install from file)
  → check logs at ~/Library/Logs/Claude/mcp*.log
```

Iterate until startup is clean. Remember that the **first** launch after a fresh install rebuilds
the `uv` environment (needs network); later launches are fast.
