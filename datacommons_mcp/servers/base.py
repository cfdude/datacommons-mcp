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
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from ..clients import create_dc_client
from ..config import load_config
from ..data_models.settings import BaseDCSettings, CustomDCSettings, DCSettingsSelector
from ..utils.output_handler import OutputHandler, OutputHandlerConfig
from ..utils.pagination_handler import PaginationHandler
from ..utils.path_resolver import PathResolver

logger = logging.getLogger(__name__)


def _get_dc_settings():
    """Get Data Commons settings from environment."""
    settings_selector = DCSettingsSelector()
    if settings_selector.dc_type == "custom":
        return CustomDCSettings()
    return BaseDCSettings()


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
    load_dotenv()
    config = load_config()
    dc_settings = _get_dc_settings()

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
)


__all__ = ["mcp"]
