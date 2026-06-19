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
"""FastMCP server base module.

This module creates the FastMCP server instance and lifespan context.
Tool modules import `mcp` from here to register their tools.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from ..clients import create_dc_client
from ..config import get_dc_settings, load_config
from ..utils.output_handler import OutputHandler, OutputHandlerConfig
from ..utils.pagination_handler import PaginationHandler
from ..utils.path_resolver import PathResolver

logger = logging.getLogger(__name__)


def _find_project_root() -> Path:
    """Locate the project/extension root (the directory containing ``pyproject.toml``).

    Walks up from this file, so it is correct in BOTH the ``src/`` dev layout
    (``src/datacommons_mcp/tools/base.py`` -> repo root) and the flattened
    extension bundle (``datacommons_mcp/tools/base.py`` -> bundle root, where
    build-extension.sh copies ``pyproject.toml``). Falls back to the directory
    containing the ``datacommons_mcp`` package if no marker is found.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parent.parent.parent


_PROJECT_ROOT = _find_project_root()


def _load_env_with_fallback() -> None:
    """Load environment variables with fallback for unresolved extension templates.

    When this server runs as a Claude extension without user_config filled in,
    DC_* env vars arrive as literal template strings like "${user_config.api_key}"
    instead of real values. This function:

    1. Detects and removes those unresolved template literals from os.environ
       so pydantic-settings doesn't treat them as real values.
    2. Searches for a .env file in multiple locations before falling back to
       the standard CWD search — necessary because CWD is unpredictable when
       launched by Claude Code or Claude Desktop.

    Search order for .env:
      - DC_STORAGE_DIR (if set and resolved)
      - Package root (alongside the installed package)
      - Current working directory
      - User home directory (~/.env)
    """
    # Strip unresolved Claude extension template literals (e.g. "${user_config.api_key}")
    unresolved = [k for k, v in os.environ.items() if k.startswith("DC_") and v.startswith("${")]
    for key in unresolved:
        logger.info(
            "Removing unresolved extension template for %s; will look for .env fallback", key
        )
        del os.environ[key]

    # Build ordered list of candidate .env paths
    candidates: list[Path] = []

    storage_dir = os.environ.get("DC_STORAGE_DIR", "")
    if storage_dir and not storage_dir.startswith("${"):
        candidates.append(Path(storage_dir) / ".env")

    candidates.append(_PROJECT_ROOT / ".env")
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path.home() / ".env")

    for path in candidates:
        if path.exists():
            logger.info("Loading .env from %s", path)
            load_dotenv(path)
            return

    # No .env found anywhere; load_dotenv with no args is a no-op but harmless
    load_dotenv()


@lifespan
async def dc_lifespan(server: FastMCP):
    """Initialize shared Data Commons resources for all tools.

    Yields a context dictionary containing:
    - config: AppConfig instance
    - dc_settings: DCSettings (BaseDCSettings or CustomDCSettings)
    - client: DCClient for API calls
    - output_handler: OutputHandler for smart output routing
    - path_resolver: PathResolver for file paths
    """
    _load_env_with_fallback()
    config = load_config()
    dc_settings = get_dc_settings()

    logger.info("Initializing Data Commons client...")
    logger.info("DC type: %s", config.dc_type)

    # Create DC client
    client = create_dc_client(dc_settings)
    logger.info("Data Commons client initialized successfully")

    # Initialize path resolver
    storage_dir = Path(config.storage_directory)
    path_resolver = PathResolver(storage_dir)

    # Initialize output handler config
    output_config = OutputHandlerConfig(
        output_format=config.output_format,
        multi_file=config.multi_file_export,
        include_lineage=config.include_lineage,
        max_pages=config.max_pages,
        storage_dir=storage_dir,
        screen_row_threshold=config.screen_row_threshold,
    )

    # Initialize output handler
    output_handler = OutputHandler(client, output_config)

    # Initialize pagination handler
    pagination_handler = PaginationHandler(
        client=client,
        path_resolver=path_resolver,
        max_pages=config.max_pages,
        include_lineage=config.include_lineage,
    )

    try:
        yield {
            # Configuration
            "config": config,
            "dc_settings": dc_settings,
            # DC client
            "client": client,
            # Utilities
            "output_handler": output_handler,
            "pagination_handler": pagination_handler,
            "path_resolver": path_resolver,
        }
    finally:
        # Cleanup if needed (DC client doesn't require async cleanup)
        logger.info("Data Commons MCP server shutting down")


# Create main FastMCP server with lifespan
mcp = FastMCP(
    name="Data Commons MCP Server",
    instructions="""
    This server provides access to the Data Commons knowledge graph for statistical data.

    Available tools:
    - search_indicators: Search for statistical variables and topic hierarchies
    - get_observations: Fetch statistical data for variables and places

    Use search_indicators first to discover available data, then use get_observations
    to fetch the actual statistical values. Large datasets are automatically saved
    to files to preserve context window.
    """,
    lifespan=dc_lifespan,
    # Mask internal error details from clients (default is False, which would
    # leak raw exception text). The tool error boundary surfaces intended
    # ToolError messages; everything else is masked.
    mask_error_details=True,
)


__all__ = ["mcp"]
