#!/bin/bash
# Entry point for the DataCommons MCP Claude Desktop extension.
# Claude Desktop uses /usr/bin/python3 (macOS system Python 3.9) by default,
# but fastmcp requires Python 3.10+. This script finds a compatible interpreter.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Search for Python 3.10+ in order of preference
for PYTHON in \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3 \
    python3.13 python3.12 python3.11 python3.10 python3; do

    if command -v "$PYTHON" &>/dev/null; then
        MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)" 2>/dev/null) || continue
        MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)" 2>/dev/null) || continue
        if [ "$MAJOR" = "3" ] && [ "$MINOR" -ge 10 ]; then
            exec "$PYTHON" "$SCRIPT_DIR/datacommons_mcp/run_server.py" "$@"
        fi
    fi
done

echo "Error: Python 3.10 or higher is required but not found." \
     "Install Python 3.10+ via Homebrew (brew install python) or python.org." >&2
exit 1
