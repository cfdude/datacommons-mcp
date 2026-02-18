#!/bin/bash
set -e

# Build script for DataCommons MCP Claude Desktop Extension
# Creates a .mcpb bundle with all dependencies for easy installation
# Tested and verified with real DataCommons API (see docs/extension-compatibility.md)

echo "Building DataCommons MCP extension..."

# Clean previous builds
rm -rf build/ 2>/dev/null || true
rm -f datacommons-mcp.mcpb 2>/dev/null || true
rm -f agent-toolkit.mcpb 2>/dev/null || true

# Create build directory structure
mkdir -p build

# Copy the source code and shell entry point
cp -r datacommons_mcp build/
cp run_server.sh build/

# Create a lib directory for dependencies
mkdir -p build/lib

# Install dependencies into the lib directory using uv
# Target Python 3.12 (/usr/local/bin/python3) for wheel compatibility.
# Claude Desktop's PATH includes /usr/local/bin before /usr/bin, so the shell
# script wrapper (run_server.sh) will pick up this interpreter, not the
# Apple system Python 3.9 at /usr/bin/python3.
echo "Installing Python dependencies..."
uv pip install \
  --target build/lib \
  --python /usr/local/bin/python3 \
  --prerelease=allow \
  "fastmcp>=3.0.0b1" requests datacommons-client pydantic pydantic-settings python-dateutil

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
