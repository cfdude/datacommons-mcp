# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""FastMCP server for Data Commons API.

This module is the entry point for the FastMCP-based Data Commons server.
It imports all tool modules to register them with the server
and provides the run function.
"""

from __future__ import annotations

import os
from pathlib import Path

# Set working directory to user's home to avoid macOS TCC prompts
# when cwd is / (root). Claude Desktop launches extensions without
# setting cwd, which causes privacy permission dialogs for every
# protected directory (Desktop, Documents, Google Drive, etc.)
if os.getcwd() == "/":
    os.chdir(Path.home())

# Import all tool modules to register their tools with the server
# The @mcp.tool decorators in each module register the tools on import
from .servers import (
    observations as _observations,  # noqa: F401
    search as _search,  # noqa: F401
)

# Import the server instance from base (this creates the mcp instance with lifespan)
from .servers.base import mcp

# Note: Unlike mcp-fred, we don't use progressive disclosure by default
# since Data Commons only has two core tools. Both are always available.
# If more tools are added later, consider using:
# mcp.disable(tags={"tier:data", "tier:advanced"})


def run_server():
    """Run the FastMCP server."""
    mcp.run()


__all__ = ["mcp", "run_server"]
