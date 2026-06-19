#!/bin/bash
set -e

# Build script for the Data Commons MCP Claude Desktop Extension
# Creates a .mcpb bundle for easy installation.
#
# Dependencies are NOT prebundled. The bundle ships the dependency *spec*
# (pyproject.toml + uv.lock); run_server.sh uses uv to build the locked
# environment against the user's Python on first launch. This keeps the
# bundle small and avoids shipping CPython-version-specific compiled wheels.

echo "Building Data Commons MCP extension..."

# Clean previous builds
rm -rf build/ 2>/dev/null || true
rm -f datacommons-mcp.mcpb 2>/dev/null || true
rm -f agent-toolkit.mcpb 2>/dev/null || true

# Create build directory structure
mkdir -p build

# Copy the source code and shell entry point. The package lives under src/ (src
# layout); copy the package itself so the bundle has `datacommons_mcp/` at its
# root (run_server.py expects the package alongside lib/). Exclude Python bytecode
# caches — they bloat the bundle and can be stale for the wrong interpreter (uv
# runs from source). rsync keeps this portable (macOS ships bash 3.2 without globstar).
rsync -a --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' \
    src/datacommons_mcp build/
# Ship both launchers: run_server.sh (macOS/Linux) and run_server.cmd (Windows).
# manifest.json selects per-platform via mcp_config.platform_overrides.
cp run_server.sh run_server.cmd build/

# Copy the dependency spec uv needs to resolve/build at runtime.
# pyproject.toml + uv.lock pin the exact dependency versions (reproducible);
# README.md and LICENSE are referenced by pyproject.toml and required to
# build the local package.
cp pyproject.toml uv.lock README.md LICENSE build/

# Copy manifest to build directory
cp manifest.json build/

# Pack from the root directory
mcpb pack build/

# Rename the output file
mv build.mcpb datacommons-mcp.mcpb

echo "✓ Extension built successfully: datacommons-mcp.mcpb"
echo "  Package size: $(du -h datacommons-mcp.mcpb | cut -f1)"
echo ""
echo "Install in Claude Desktop:"
echo "  Settings → Developer → Extensions → Install from .mcpb file"
echo "  Select: datacommons-mcp.mcpb"
