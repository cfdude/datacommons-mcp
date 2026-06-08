#!/bin/bash
# Entry point for the Data Commons MCP Claude Desktop extension.
#
# Dependencies are NOT bundled. Instead, uv resolves them from the bundled
# pyproject.toml + uv.lock and builds native wheels for whatever Python the
# user has (subject to requires-python in pyproject.toml). This avoids shipping
# version-specific compiled extensions (.so) that only load on one CPython
# minor version. The locked versions in uv.lock make every install reproducible.
#
# First launch downloads + builds the dependency environment (cached afterward),
# so it requires network access. uv is expected to be on PATH.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Claude Desktop launches this from a GUI process whose PATH is the minimal
# launchd default (/usr/bin:/bin:...) — it does NOT include ~/.local/bin
# (uv's standalone-installer default) or Homebrew bins. So we can't rely on a
# bare `uv` being resolvable; search known install locations by absolute path
# (PATH lookup last, for terminal/dev launches).
UV=""
for candidate in \
    "$HOME/.local/bin/uv" \
    /opt/homebrew/bin/uv \
    /usr/local/bin/uv \
    "$(command -v uv 2>/dev/null)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        UV="$candidate"
        break
    fi
done

if [ -z "$UV" ]; then
    echo "Error: 'uv' was not found." \
         "The Data Commons MCP extension uses uv to resolve its Python" \
         "dependencies at runtime. Install it from https://docs.astral.sh/uv/" \
         "(or have it deployed via your organization's tooling) and try again." >&2
    exit 1
fi

# --frozen: install exactly what's pinned in uv.lock; never re-resolve.
exec "$UV" run --frozen --project "$SCRIPT_DIR" \
    python "$SCRIPT_DIR/datacommons_mcp/run_server.py" "$@"
