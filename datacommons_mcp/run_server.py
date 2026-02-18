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
"""Standalone entry point for the Data Commons MCP server.

This script is used by the Claude Desktop extension manifest, which runs:
    python ${__dirname}/datacommons_mcp/run_server.py

Running as a script (rather than a module) means relative imports won't work
without first adding the package root to sys.path.
"""

import os
import sys
from pathlib import Path

# Add the package root and bundled lib/ directory to sys.path.
# When installed as a Claude Desktop extension, dependencies are bundled
# in a lib/ directory alongside the datacommons_mcp package:
#   <extension_root>/
#     datacommons_mcp/   <- this file lives here
#     lib/               <- fastmcp, pydantic, etc. live here
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "lib"))

if __name__ == "__main__":
    from datacommons_mcp.fastmcp_server import run_server

    run_server()
