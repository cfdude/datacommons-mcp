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
"""FastMCP server modules for Data Commons MCP.

This package contains the FastMCP server implementation following
FastMCP 3.0.0b1 patterns. Each module registers its tools with
the shared `mcp` instance from base.py.
"""

from .base import mcp
from .common import (
    get_client,
    get_config,
    tool_error_boundary,
)

# Tool modules are imported by fastmcp_server.py to register their tools

__all__ = [
    "get_client",
    "get_config",
    "mcp",
    "tool_error_boundary",
]
